from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import uuid
import os

app = Flask(__name__)

# Segurança
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "troque-esta-chave-depois")

# Banco (SQLite funciona, mas em host grátis pode não persistir para sempre)
# Para persistência real no futuro: usar Postgres do Render
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///financeiro.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


def gen_uid(prefix: str) -> str:
    return f"{prefix}-" + uuid.uuid4().hex[:10].upper()


# -------------------- MODELOS --------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(90), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), nullable=False, default=lambda: gen_uid("ACC"))
    name = db.Column(db.String(140), nullable=False)
    balance = db.Column(db.Float, nullable=False, default=0.0)


class Creditor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), nullable=False, default=lambda: gen_uid("CRD"))
    name = db.Column(db.String(160), nullable=False)
    ctype = db.Column(db.String(20), nullable=False, default="EMPRESA")  # EMPRESA/PESSOA/BANCO


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), nullable=False, default=lambda: gen_uid("TRX"))
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    account = db.relationship("Account")
    description = db.Column(db.String(220), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # positivo entra / negativo sai
    tdate = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD


class PendingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), nullable=False, default=lambda: gen_uid("PEN"))

    # PAGAR / RECEBER / EMPRESTIMO
    kind = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="ABERTO")  # ABERTO / PAGO

    title = db.Column(db.String(240), nullable=False)
    due_date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    amount = db.Column(db.Float, nullable=False)

    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    account = db.relationship("Account")

    creditor_id = db.Column(db.Integer, db.ForeignKey("creditor.id"), nullable=True)
    creditor = db.relationship("Creditor")

    paid_amount = db.Column(db.Float, nullable=True)
    diff_interest_or_discount = db.Column(db.Float, nullable=True)  # pago - original


# -------------------- LOGIN --------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def bootstrap_defaults():
    # cria usuário padrão
    if not User.query.filter_by(username="admin").first():
        db.session.add(
            User(username="admin", password_hash=generate_password_hash("admin123"))
        )

    # conta padrão
    if Account.query.count() == 0:
        db.session.add(Account(name="Conta Principal", balance=0.0))

    db.session.commit()


@app.before_request
def ensure_db():
    db.create_all()
    bootstrap_defaults()


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Usuário ou senha inválidos.")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# -------------------- PÁGINAS --------------------
@app.route("/")
@login_required
def dashboard():
    contas = Account.query.all()
    saldo_total = sum(a.balance for a in contas)

    pend_abertas = PendingItem.query.filter(PendingItem.status != "PAGO").count()
    credores = Creditor.query.count()
    ultimas = Transaction.query.order_by(Transaction.id.desc()).limit(10).all()

    kpis = {
        "saldo_total": saldo_total,
        "pendencias_abertas": pend_abertas,
        "credores": credores
    }

    return render_template(
        "dashboard.html",
        title="Dashboard",
        header="Dashboard",
        subtitle="Visão geral do seu financeiro",
        active="dashboard",
        kpis=kpis,
        ultimas=ultimas
    )


@app.route("/pendencias")
@login_required
def pendencias():
    pend = PendingItem.query.order_by(PendingItem.due_date.asc()).all()
    contas = Account.query.order_by(Account.name.asc()).all()
    credores = Creditor.query.order_by(Creditor.name.asc()).all()

    return render_template(
        "pendencias.html",
        title="Pendências",
        header="Pendências",
        subtitle="Central de tudo que ainda está pendente (como você pediu)",
        active="pendencias",
        pendencias=pend,
        contas=contas,
        credores=credores
    )


@app.post("/pendencias/create")
@login_required
def pendencias_create():
    title = request.form["title"].strip()
    due_date = request.form["due_date"]
    amount = float(request.form["amount"])
    kind = request.form["kind"]
    account_id = int(request.form["account_id"])
    creditor_id = request.form.get("creditor_id") or None

    p = PendingItem(
        title=title,
        due_date=due_date,
        amount=amount,
        kind=kind,
        account_id=account_id,
        creditor_id=int(creditor_id) if creditor_id else None
    )
    db.session.add(p)
    db.session.commit()
    return redirect(url_for("pendencias"))


@app.post("/pendencias/<int:pending_id>/pay")
@login_required
def pendencias_pay(pending_id):
    p = db.session.get(PendingItem, pending_id)
    if not p or p.status == "PAGO":
        return redirect(url_for("pendencias"))

    paid_amount = float(request.form["paid_amount"])
    p.paid_amount = paid_amount
    p.diff_interest_or_discount = paid_amount - p.amount
    p.status = "PAGO"

    acc = db.session.get(Account, p.account_id)

    # regra de dinheiro real:
    # PAGAR/EMPRESTIMO => saída (negativo)
    # RECEBER => entrada (positivo)
    if p.kind in ("PAGAR", "EMPRESTIMO"):
        trx_amount = -abs(paid_amount)
    else:
        trx_amount = abs(paid_amount)

    acc.balance += trx_amount

    trx = Transaction(
        account_id=acc.id,
        description=f"[{p.kind}] {p.title}",
        amount=trx_amount,
        tdate=str(date.today())
    )

    db.session.add(trx)
    db.session.commit()
    return redirect(url_for("pendencias"))


@app.route("/contas")
@login_required
def contas():
    contas = Account.query.order_by(Account.name.asc()).all()
    ultimas = Transaction.query.order_by(Transaction.id.desc()).limit(12).all()
    return render_template(
        "contas.html",
        title="Contas",
        header="Contas bancárias",
        subtitle="Cada conta com seu extrato separado",
        active="contas",
        contas=contas,
        ultimas=ultimas
    )


@app.post("/contas/create")
@login_required
def contas_create():
    name = request.form["name"].strip()
    opening_balance = float(request.form["opening_balance"])
    db.session.add(Account(name=name, balance=opening_balance))
    db.session.commit()
    return redirect(url_for("contas"))


@app.route("/credores")
@login_required
def credores():
    cred = Creditor.query.order_by(Creditor.name.asc()).all()
    return render_template(
        "credores.html",
        title="Credores",
        header="Credores",
        subtitle="Cadastre e use nos lançamentos/pendências",
        active="credores",
        credores=cred
    )


@app.post("/credores/create")
@login_required
def credores_create():
    name = request.form["name"].strip()
    ctype = request.form["ctype"]
    db.session.add(Creditor(name=name, ctype=ctype))
    db.session.commit()
    return redirect(url_for("credores"))


@app.route("/cartoes")
@login_required
def cartoes():
    return render_template(
        "cartoes.html",
        title="Cartões",
        header="Cartões",
        subtitle="Base pronta (próxima etapa: faturas e fechamento)",
        active="cartoes"
    )


@app.route("/veiculos")
@login_required
def veiculos():
    return render_template(
        "veiculos.html",
        title="Veículos",
        header="Veículos",
        subtitle="Histórico separado do caixa (como você pediu)",
        active="veiculos"
    )


@app.route("/documentos")
@login_required
def documentos():
    return render_template(
        "documentos.html",
        title="Documentos",
        header="Documentos",
        subtitle="Base para anexos e documentos pessoais",
        active="documentos"
    )


@app.route("/relatorios")
@login_required
def relatorios():
    return render_template(
        "relatorios.html",
        title="Relatórios",
        header="Relatórios",
        subtitle="Base para PDF e análises (próxima etapa)",
        active="relatorios"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
