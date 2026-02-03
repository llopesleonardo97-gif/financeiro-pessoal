from flask import Flask, render_template_string, request, redirect
import sqlite3, uuid, datetime

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect("financeiro.db")
    conn.row_factory = sqlite3.Row
    return conn

def gerar_id():
    return "FIN-" + uuid.uuid4().hex[:8].upper()

@app.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        descricao = request.form["descricao"]
        valor = float(request.form["valor"])
        tipo = request.form["tipo"]
        vencimento = request.form["vencimento"]
        pago = request.form.get("pago", "não")

        db.execute(
            "INSERT INTO lancamentos (id_rastreio, descricao, valor, tipo, vencimento, pago) VALUES (?,?,?,?,?,?)",
            (gerar_id(), descricao, valor, tipo, vencimento, pago)
        )
        db.commit()
        return redirect("/")

    lancamentos = db.execute("SELECT * FROM lancamentos ORDER BY vencimento").fetchall()

    return render_template_string("""
    <html>
    <head>
        <title>Financeiro Pessoal</title>
        <style>
            body { font-family: Arial; background:#fff; padding:20px }
            h1 { color:#C9A24D }
            input, select { padding:6px; margin:4px }
            button { background:#C9A24D; color:white; padding:8px; border:none }
            table { width:100%; margin-top:20px; border-collapse: collapse }
            th, td { border-bottom:1px solid #ddd; padding:8px }
        </style>
    </head>
    <body>
        <h1>Financeiro Pessoal</h1>

        <form method="post">
            <input name="descricao" placeholder="Descrição" required>
            <input name="valor" placeholder="Valor" required>
            <input name="vencimento" type="date" required>
            <select name="tipo">
                <option value="Pagar">A Pagar</option>
                <option value="Receber">A Receber</option>
            </select>
            <button>Salvar</button>
        </form>

        <table>
            <tr>
                <th>ID</th>
                <th>Descrição</th>
                <th>Valor</th>
                <th>Tipo</th>
                <th>Vencimento</th>
            </tr>
            {% for l in lancamentos %}
            <tr>
                <td>{{l.id_rastreio}}</td>
                <td>{{l.descricao}}</td>
                <td>R$ {{l.valor}}</td>
                <td>{{l.tipo}}</td>
                <td>{{l.vencimento}}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """, lancamentos=lancamentos)

if __name__ == "__main__":
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
