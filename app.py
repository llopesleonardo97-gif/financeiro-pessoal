from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import uuid, os
from datetime import date

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "troque-esta-chave-depois")

# SQLite (no Render grátis pode resetar em redeploy)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///financeiro.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

def gen_uid(prefix="FIN"):
    return f"{prefix}-" + uuid.uuid4().hex[:8].upper()

# ----------------- MODELS -----------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    balance = db.Column(db.Float, nullable=False, default=0.0)

class Creditor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    ctype = db.Column(db.String(20), nullable=False, default="EMPRESA")

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), nullable=False, default=lambda: gen_uid("TRX"))
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    account = db.relationship("Account")
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # positivo entra, negativo sai
    date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD

class PendingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), nullable=False, default=lambda: gen_uid("PEN"))
    kind = db.Column(db.String(20), nullable=False)      # PAGAR / RECEBER / EMPRESTIMO
    status = db.Column(db.String(20), nullable=False, default="ABERTO")  # ABERTO / PAGO
    title = db.Column(db.String(220), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    account = db.relationship("Account")
    creditor_id = db.Column(db.Integer, db.ForeignKey("creditor.id"), nullable=True)
    creditor = db.relationship("Creditor")

    # pagamento
    paid_amount = db.Column(db.Float, nullable=True)
    diff_interest_or_discount = db.Column(db.Float, nullable=True)  # pago - original

# ----------------- LOGIN -----------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def ensure_default_data():
    # Usuário padrão
    if not User.query.filter_by(username="admin").first():
        u = User(username="admin", password_hash=generate_password_hash("admin123"))
        db.session.add(u)

    # Conta padrão
    if Account.query.count() == 0:
        db.session.add(Account(name="Conta Principal", balance=0.0))

    db.session.commit()

@app.before_request
def boot():
    db.create_all()
    ensure_default_data()

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

# ----------------- PAGES -----------------
@app.route("/")
@login_required
def dashboard():
    # KPIs
    contas = Account.query.all()
    saldo_total = sum(a.balance for a in contas)

    pend_abertas = PendingItem.query.filter(PendingItem.status != "PAGO").count()
    credores = Creditor.query.count()

    ultimas = Transaction.query.order_by(Transaction.id.desc()).limit(10).all()

    class KPIs: pass
    k = KPIs()
    k.saldo_total = saldo_total
    k.pendencias_abertas = pend_abertas
    k.credores = credores

    return render_template(
        "dashboard.html",
        title="Dashboard",
        header="Dashboard",
        subtitle="Visão geral do seu financeiro",
        active="dashboard",
        kpis=k,
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
        subtitle="Central de tudo que ainda está em aberto (como você pediu)",
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
        kind=kind,
        title=title,
        due_date=due_date,
        amount=amount,
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

    # cria lançamento real na conta (não mistura antes de pagar)
    acc = db.session.get(Account, p.account_id)

    # regra: PAGAR/EMPRESTIMO = saída (negativo), RECEBER = entrada (positivo)
    if p.kind in ("PAGAR", "EMPRESTIMO"):
        trx_amount = -abs(paid_amount)
    else:
        trx_amount = abs(paid_amount)

    # atualiza saldo
    acc.balance += trx_amount

    trx = Transaction(
        account_id=acc.id,
        description=f"[{p.kind}] {p.title}",
        amount=trx_amount,
        date=str(date.today())
    )
    db.session.add(trx)
    db.session.commit()
    return redirect(url_for("pendencias"))

@app.route("/contas")
@login_required
def contas():
    contas = Account.query.order_by(Account.name.asc()).all()
    return render_template(
        "contas.html",
        title="Contas",
        header="Contas bancárias",
        subtitle="Cada conta com seu próprio extrato (separado, como você pediu)",
        active="contas",
        contas=contas
    )

@app.post("/contas/create")
@login_required
def contas_create():
    name = request.form["name"].strip()
    opening_balance = float(request.form["opening_balance"])
    a = Account(name=name, balance=opening_balance)
    db.session.add(a)
    db.session.commit()
    return redirect(url_for("contas"))

@app.route("/contas/<int:account_id>")
@login_required
def conta_detail(account_id):
    # Página simples: lista de transações da conta
    a = db.session.get(Account, account_id)
    if not a:
        return redirect(url_for("contas"))

    tx = Transaction.query.filter_by(account_id=a.id).order_by(Transaction.id.desc()).limit(50).all()

    # Render rápido sem template extra (mantém simples v1)
    rows = "".join([f"<tr><td>{t.uid}</td><td>{t.description}</td><td>R$ {t.amount:.2f}</td><td>{t.date}</td></tr>" for t in tx]) or "<tr><td colspan='4'><small>Sem lançamentos ainda.</small></td></tr>"

    return f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <link rel="stylesheet" href="{url_for('static', filename='style.css')}">
      <title>Extrato • {a.name}</title>
    </head>
    <body>
      <div class="layout">
        <aside class="sidebar">
          <div class="brand"><div class="brand-badge"></div><div><h1>Financeiro Pessoal</h1><p>Extrato</p></div></div>
          <nav class="nav">
            <a href="{url_for('dashboard')}"><span class="dot"></span> Dashboard</a>
            <a href="{url_for('pendencias')}"><span class="dot"></span> Pendências</a>
            <a href="{url_for('contas')}" class="active"><span class="dot"></span> Contas bancárias</a>
            <a href="{url_for('cartoes')}"><span class="dot"></span> Cartões</a>
            <a href="{url_for('credores')}"><span class="dot"></span> Credores</a>
            <a href="{url_for('veiculos')}"><span class="dot"></span> Veículos</a>
            <a href="{url_for('documentos')}"><span class="dot"></span> Documentos</a>
            <a href="{url_for('relatorios')}"><span class="dot"></span> Relatórios</a>
          </nav>
          <div class="sidebar-footer"><span>{current_user.username}</span><a href="{url_for('logout')}" style="color:var(--gold);font-weight:800;">Sair</a></div>
        </aside>

        <main class="main">
          <div class="topbar">
            <div class="title">
              <h2>{a.name}</h2>
              <p>Saldo: R$ {a.balance:.2f}</p>
            </div>
            <div class="split">
              <a class="btn secondary" href="{url_for('contas')}">Voltar</a>
            </div>
          </div>

          <div class="card">
            <h3>Últimos lançamentos desta conta</h3>
            <table class="table">
              <thead><tr><th>ID</th><th>Descrição</th><th>Valor</th><th>Data</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
            <p style="margin-top:10px;"><small>Movimentações aparecem aqui somente quando você conclui uma pendência (paga/recebe).</small></p>
          </div>
        </main>
      </div>
    </body>
    </html>
    """

@app.route("/cartoes")
@login_required
def cartoes():
    return render_template(
        "cartoes.html",
        title="Cartões",
        header="Cartões",
        subtitle="Base pronta para faturas e fechamento (próxima etapa)",
        active="cartoes"
    )

@app.route("/credores")
@login_required
def credores():
    cred = Creditor.query.order_by(Creditor.name.asc()).all()
    return render_template(
        "credores.html",
        title="Credores",
        header="Credores",
        subtitle="Cadastre empresas/bancos/pessoas e vincule às pendências",
        active="credores",
        credores=cred
    )

@app.post("/credores/create")
@login_required
def credores_create():
    name = request.form["name"].strip()
    ctype = request.form["ctype"]
    c = Creditor(name=name, ctype=ctype)
    db.session.add(c)
    db.session.commit()
    return redirect(url_for("credores"))

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
        subtitle="Base para anexos e arquivos pessoais",
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

# ----------------- RUN -----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
