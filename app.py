from flask import Flask, render_template_string, request, redirect
import sqlite3
import uuid
import os

app = Flask(__name__)

# ---------- BANCO DE DADOS ----------
def get_db():
    conn = sqlite3.connect("financeiro.db")
    conn.row_factory = sqlite3.Row
    return conn

def gerar_id():
    return "FIN-" + uuid.uuid4().hex[:8].upper()

# ---------- ROTAS ----------
@app.route("/", methods=["GET", "POST"])
def index():
    db = get_db()

    if request.method == "POST":
        descricao = request.form["descricao"]
        valor = float(request.form["valor"])
        tipo = request.form["tipo"]
        vencimento = request.form["vencimento"]

        db.execute(
            """
            INSERT INTO lancamentos 
            (id_rastreio, descricao, valor, tipo, vencimento)
            VALUES (?, ?, ?, ?, ?)
            """,
            (gerar_id(), descricao, valor, tipo, vencimento)
        )
        db.commit()
        return redirect("/")

    lancamentos = db.execute(
        "SELECT * FROM lancamentos ORDER BY vencimento"
    ).fetchall()

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Financeiro Pessoal</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #ffffff;
                padding: 30px;
            }
            h1 {
                color: #C9A24D;
            }
            input, select {
                padding: 8px;
                margin: 5px;
            }
            button {
                background: #C9A24D;
                color: white;
                padding: 10px 15px;
                border: none;
                cursor: pointer;
            }
            table {
                width: 100%;
                margin-top: 20px;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                border-bottom: 1px solid #ddd;
                text-align: left;
            }
        </style>
    </head>
    <body>

        <h1>Financeiro Pessoal</h1>

        <form method="post">
            <input name="descricao" placeholder="Descrição" required>
            <input name="valor" type="number" step="0.01" placeholder="Valor" required>
            <input name="vencimento" type="date" required>
            <select name="tipo">
                <option value="A Pagar">A Pagar</option>
                <option value="A Receber">A Receber</option>
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
                <td>{{ l.id_rastreio }}</td>
                <td>{{ l.descricao }}</td>
                <td>R$ {{ "%.2f"|format(l.valor) }}</td>
                <td>{{ l.tipo }}</td>
                <td>{{ l.vencimento }}</td>
            </tr>
            {% endfor %}
        </table>

    </body>
    </html>
    """, lancamentos=lancamentos)

# ---------- INICIALIZAÇÃO ----------
if __name__ == "__main__":
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_rastreio TEXT,
            descricao TEXT,
            valor REAL,
            tipo TEXT,
            vencimento TEXT
        )
    """)
    db.commit()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
