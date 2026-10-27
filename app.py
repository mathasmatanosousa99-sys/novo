import os
import re
import secrets
import sqlite3
import time
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "avicenna.db")
UPLOAD_DIR = os.path.join(BASE, "static", "uploads")
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

# Chave secreta persistente, criada na primeira execução
_key_file = os.path.join(BASE, ".secret_key")
if not os.path.exists(_key_file):
    with open(_key_file, "w") as f:
        f.write(secrets.token_hex(32))
with open(_key_file) as f:
    app.secret_key = f.read().strip()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

DEFAULT_SETTINGS = {
    "ano_lectivo": "2027",
    "slogan": "Formamos com elevada competência técnica para melhor servir e estar sempre presente no mercado competitivo",
    "hero_titulo": "Formamos profissionais de saúde com",
    "hero_destaque": "competência técnica",
    "hero_texto": "O Instituto de Saúde Avicenna prepara técnicos de saúde em Nampula, com aulas teóricas, prática em laboratório e acompanhamento de perto em cada curso.",
    "telefone1": "843972038",
    "telefone2": "879921111",
    "telefone3": "870041111",
    "telefone4": "875657726",
    "email": "",
    "cidade": "Nampula",
    "endereco": "Avenida Eduardo Mondlane (próximo ao embondeiro dos 4 caminhos via Farmácia Amurrane)",
    "horario": "Segunda a Sexta, das 7h30 às 16h00",
    "sobre_titulo": "Uma escola de saúde feita para servir a comunidade",
    "sobre_texto": "O Instituto de Saúde Avicenna é uma instituição de ensino técnico de saúde sediada em Nampula. Recebemos estudantes de toda a região e formamos enfermeiros e técnicos de medicina que levam competência, humanidade e responsabilidade aos serviços de saúde do país.",
    "missao": "Formar profissionais de saúde com elevada competência técnica e valores humanos, capazes de servir a comunidade com qualidade e de estar sempre presentes no mercado competitivo.",
    "visao": "Ser uma referência em Nampula e em Moçambique na formação técnica em saúde, reconhecida pela qualidade do ensino, pela prática e pela empregabilidade dos seus formandos.",
    "valores": "Competência técnica|Ética e responsabilidade|Respeito pela vida|Compromisso com a comunidade|Disciplina e excelência|Humanidade no cuidado",
    "fizemos": "Formámos turmas de enfermagem e medicina geral em Nampula|Montámos salas de prática com modelos anatómicos e manequins de simulação|Construímos instalações próprias, amplas e preparadas para o ensino|Realizámos cerimónias e actividades académicas com a participação dos estudantes",
}

SEED_COURSES = [
    ("Enfermagem de Saúde Materna Infantil",
     "Formação focada no cuidado da mulher, da grávida, do parto e da criança, com prática em sala de simulação de partos e cuidados ao recém nascido.",
     "materno.jpg", 1),
    ("Enfermagem Geral",
     "Formação ampla em cuidados de enfermagem, anatomia, procedimentos clínicos e atendimento ao paciente, com aulas práticas com modelos anatómicos.",
     "modelos.jpg", 2),
    ("Técnico de Medicina Geral",
     "Formação para o diagnóstico, tratamento e acompanhamento de doenças comuns nas unidades sanitárias, com forte componente clínica e laboratorial.",
     "pratica.jpg", 3),
]

SEED_GALLERY = [
    ("Fachada do Instituto", "fachada.jpg"),
    ("Pátio e blocos de aulas", "patio.jpg"),
    ("Estudantes a caminho das aulas", "galeria1.jpg"),
    ("Estudantes sorridentes", "galeria2.jpg"),
    ("Momento entre colegas", "galeria3.jpg"),
    ("Cerimónia académica", "galeria4.jpg"),
    ("Estudantes na cerimónia", "galeria5.jpg"),
    ("Turma reunida", "galeria6.jpg"),
    ("Aula prática", "galeria7.jpg"),
    ("Sala de aula", "sala.jpg"),
    ("Prática de enfermagem materna", "materno.jpg"),
    ("Sala de simulação", "infantil.jpg"),
    ("Modelos anatómicos", "modelos.jpg"),
    ("Aula de anatomia", "pratica.jpg"),
]


# ---------------------------------------------------------------- base de dados
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT NOT NULL DEFAULT '',
            duracao TEXT NOT NULL DEFAULT '',
            inscricao REAL NOT NULL DEFAULT 0,
            matricula REAL NOT NULL DEFAULT 0,
            mensalidade REAL NOT NULL DEFAULT 0,
            imagem TEXT NOT NULL DEFAULT '',
            ordem INTEGER NOT NULL DEFAULT 0,
            ativo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL DEFAULT '',
            ficheiro TEXT NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            curso TEXT NOT NULL DEFAULT '',
            mensagem TEXT NOT NULL DEFAULT '',
            criado TEXT NOT NULL,
            lido INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    for k, v in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings (chave, valor) VALUES (?, ?)", (k, v))
    if db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
        for nome, desc, img, ordem in SEED_COURSES:
            db.execute(
                "INSERT INTO courses (nome, descricao, duracao, imagem, ordem) VALUES (?,?,?,?,?)",
                (nome, desc, "", img, ordem),
            )
    if db.execute("SELECT COUNT(*) FROM gallery").fetchone()[0] == 0:
        for i, (titulo, f) in enumerate(SEED_GALLERY):
            db.execute("INSERT INTO gallery (titulo, ficheiro, ordem) VALUES (?,?,?)", (titulo, f, i))
    if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        db.execute(
            "INSERT INTO admins (usuario, senha) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123")),
        )
    db.commit()
    db.close()


def settings():
    rows = get_db().execute("SELECT chave, valor FROM settings").fetchall()
    data = dict(DEFAULT_SETTINGS)
    data.update({r["chave"]: r["valor"] for r in rows})
    return data


# ---------------------------------------------------------------- utilitários
def mzn(valor):
    """Formata preço em meticais. Zero significa a consultar."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "A consultar"
    if v <= 0:
        return "A consultar"
    texto = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    if texto.endswith(",00"):
        texto = texto[:-3]
    return f"{texto} MT"


def parse_preco(texto):
    texto = (texto or "").strip().replace("MT", "").replace(" ", "")
    if not texto:
        return 0.0
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        v = float(texto)
    except ValueError:
        return 0.0
    return max(v, 0.0)


def fone(numero):
    n = re.sub(r"\D", "", numero or "")
    if len(n) == 9:
        return f"{n[:2]} {n[2:5]} {n[5:]}"
    return numero or ""


def save_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    nome = secure_filename(file_storage.filename)
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in ALLOWED_EXT:
        return None
    final = f"{int(time.time())}_{secrets.token_hex(3)}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, final))
    return final


def img_url(ficheiro):
    if not ficheiro:
        return url_for("static", filename="img/fachada.jpg")
    if os.path.exists(os.path.join(UPLOAD_DIR, ficheiro)):
        return url_for("static", filename="uploads/" + ficheiro)
    return url_for("static", filename="img/" + ficheiro)


app.jinja_env.filters["mzn"] = mzn
app.jinja_env.filters["fone"] = fone
app.jinja_env.globals["img_url"] = img_url


# ---------------------------------------------------------------- segurança
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_post():
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not sent or sent != session.get("csrf"):
            abort(400)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*a, **kw)

    return wrapped


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


# ---------------------------------------------------------------- site público
@app.route("/")
def index():
    db = get_db()
    cursos = db.execute("SELECT * FROM courses WHERE ativo=1 ORDER BY ordem, id").fetchall()
    galeria = db.execute("SELECT * FROM gallery ORDER BY ordem, id").fetchall()
    s = settings()
    return render_template(
        "index.html",
        s=s,
        cursos=cursos,
        galeria=galeria,
        valores=[v for v in s["valores"].split("|") if v.strip()],
        fizemos=[v for v in s["fizemos"].split("|") if v.strip()],
        telefones=[s[k] for k in ("telefone1", "telefone2", "telefone3", "telefone4") if s.get(k)],
    )


@app.route("/pre-inscricao", methods=["POST"])
def pre_inscricao():
    nome = request.form.get("nome", "").strip()[:120]
    telefone = request.form.get("telefone", "").strip()[:30]
    curso = request.form.get("curso", "").strip()[:150]
    mensagem = request.form.get("mensagem", "").strip()[:800]
    if len(nome) < 3 or len(re.sub(r"\D", "", telefone)) < 9:
        flash("Preencha o nome e um número de telefone válido.", "erro")
        return redirect(url_for("index") + "#inscricao")
    db = get_db()
    db.execute(
        "INSERT INTO leads (nome, telefone, curso, mensagem, criado) VALUES (?,?,?,?,datetime('now','localtime'))",
        (nome, telefone, curso, mensagem),
    )
    db.commit()
    flash("Pré inscrição enviada. Entraremos em contacto consigo em breve.", "ok")
    return redirect(url_for("index") + "#inscricao")


# ---------------------------------------------------------------- painel admin
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        row = get_db().execute("SELECT * FROM admins WHERE usuario=?", (usuario,)).fetchone()
        if row and check_password_hash(row["senha"], senha):
            session.clear()
            session["admin"] = row["usuario"]
            csrf_token()
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin_home"))
        time.sleep(0.8)
        flash("Usuário ou senha incorretos.", "erro")
    return render_template("admin_login.html")


@app.route("/admin/sair", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_home():
    db = get_db()
    return render_template(
        "admin_home.html",
        cursos=db.execute("SELECT * FROM courses ORDER BY ordem, id").fetchall(),
        total_leads=db.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
        novos=db.execute("SELECT COUNT(*) FROM leads WHERE lido=0").fetchone()[0],
        total_galeria=db.execute("SELECT COUNT(*) FROM gallery").fetchone()[0],
        s=settings(),
        pagina="home",
    )


@app.route("/admin/cursos", methods=["GET", "POST"])
@login_required
def admin_cursos():
    db = get_db()
    if request.method == "POST":
        cid = request.form.get("id", "")
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("O nome do curso é obrigatório.", "erro")
            return redirect(url_for("admin_cursos"))
        campos = dict(
            nome=nome[:150],
            descricao=request.form.get("descricao", "").strip()[:700],
            duracao=request.form.get("duracao", "").strip()[:80],
            inscricao=parse_preco(request.form.get("inscricao")),
            matricula=parse_preco(request.form.get("matricula")),
            mensalidade=parse_preco(request.form.get("mensalidade")),
            ordem=int(request.form.get("ordem") or 0),
            ativo=1 if request.form.get("ativo") else 0,
        )
        nova = save_image(request.files.get("imagem"))
        if cid:
            if nova:
                campos["imagem"] = nova
            sets = ", ".join(f"{k}=?" for k in campos)
            db.execute(f"UPDATE courses SET {sets} WHERE id=?", (*campos.values(), cid))
            flash("Curso atualizado.", "ok")
        else:
            campos["imagem"] = nova or ""
            cols = ", ".join(campos)
            marks = ", ".join("?" for _ in campos)
            db.execute(f"INSERT INTO courses ({cols}) VALUES ({marks})", tuple(campos.values()))
            flash("Curso adicionado.", "ok")
        db.commit()
        return redirect(url_for("admin_cursos"))
    return render_template(
        "admin_cursos.html",
        cursos=db.execute("SELECT * FROM courses ORDER BY ordem, id").fetchall(),
        s=settings(),
        pagina="cursos",
    )


@app.route("/admin/cursos/<int:cid>/apagar", methods=["POST"])
@login_required
def admin_curso_apagar(cid):
    db = get_db()
    db.execute("DELETE FROM courses WHERE id=?", (cid,))
    db.commit()
    flash("Curso removido.", "ok")
    return redirect(url_for("admin_cursos"))


@app.route("/admin/precos", methods=["POST"])
@login_required
def admin_precos():
    """Atualiza os preços de todos os cursos de uma vez."""
    db = get_db()
    for c in db.execute("SELECT id FROM courses").fetchall():
        cid = c["id"]
        db.execute(
            "UPDATE courses SET inscricao=?, matricula=?, mensalidade=? WHERE id=?",
            (
                parse_preco(request.form.get(f"inscricao_{cid}")),
                parse_preco(request.form.get(f"matricula_{cid}")),
                parse_preco(request.form.get(f"mensalidade_{cid}")),
                cid,
            ),
        )
    db.commit()
    flash("Preços guardados e já visíveis no site.", "ok")
    return redirect(url_for("admin_precos_page"))


@app.route("/admin/precos")
@login_required
def admin_precos_page():
    db = get_db()
    return render_template(
        "admin_precos.html",
        cursos=db.execute("SELECT * FROM courses ORDER BY ordem, id").fetchall(),
        s=settings(),
        pagina="precos",
    )


TEXT_FIELDS = [
    "ano_lectivo", "slogan", "hero_titulo", "hero_destaque", "hero_texto",
    "telefone1", "telefone2", "telefone3", "telefone4", "email", "cidade",
    "endereco", "horario", "sobre_titulo", "sobre_texto", "missao", "visao",
    "valores", "fizemos",
]


@app.route("/admin/site", methods=["GET", "POST"])
@login_required
def admin_site():
    db = get_db()
    if request.method == "POST":
        for k in TEXT_FIELDS:
            if k in request.form:
                valor = request.form.get(k, "").strip()
                if k in ("valores", "fizemos"):
                    linhas = [l.strip() for l in valor.splitlines() if l.strip()]
                    valor = "|".join(linhas)
                db.execute(
                    "INSERT INTO settings (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                    (k, valor[:1500]),
                )
        db.commit()
        flash("Informações do site guardadas.", "ok")
        return redirect(url_for("admin_site"))
    s = settings()
    s["valores_txt"] = "\n".join(v for v in s["valores"].split("|") if v)
    s["fizemos_txt"] = "\n".join(v for v in s["fizemos"].split("|") if v)
    return render_template("admin_site.html", s=s, pagina="site")


@app.route("/admin/galeria", methods=["GET", "POST"])
@login_required
def admin_galeria():
    db = get_db()
    if request.method == "POST":
        enviados = 0
        titulo = request.form.get("titulo", "").strip()[:120]
        for f in request.files.getlist("fotos"):
            nome = save_image(f)
            if nome:
                ordem = db.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM gallery").fetchone()[0]
                db.execute(
                    "INSERT INTO gallery (titulo, ficheiro, ordem) VALUES (?,?,?)",
                    (titulo, nome, ordem),
                )
                enviados += 1
        db.commit()
        flash(f"{enviados} foto(s) adicionada(s)." if enviados else "Nenhuma foto válida enviada (use JPG, PNG ou WEBP).",
              "ok" if enviados else "erro")
        return redirect(url_for("admin_galeria"))
    return render_template(
        "admin_galeria.html",
        fotos=db.execute("SELECT * FROM gallery ORDER BY ordem, id").fetchall(),
        s=settings(),
        pagina="galeria",
    )


@app.route("/admin/galeria/<int:fid>/apagar", methods=["POST"])
@login_required
def admin_foto_apagar(fid):
    db = get_db()
    row = db.execute("SELECT ficheiro FROM gallery WHERE id=?", (fid,)).fetchone()
    if row:
        caminho = os.path.join(UPLOAD_DIR, row["ficheiro"])
        if os.path.exists(caminho):
            os.remove(caminho)
        db.execute("DELETE FROM gallery WHERE id=?", (fid,))
        db.commit()
        flash("Foto removida da galeria.", "ok")
    return redirect(url_for("admin_galeria"))


@app.route("/admin/pre-inscricoes", methods=["GET", "POST"])
@login_required
def admin_leads():
    db = get_db()
    if request.method == "POST":
        acao = request.form.get("acao")
        lid = request.form.get("id")
        if acao == "lido":
            db.execute("UPDATE leads SET lido=1 WHERE id=?", (lid,))
        elif acao == "apagar":
            db.execute("DELETE FROM leads WHERE id=?", (lid,))
        db.commit()
        return redirect(url_for("admin_leads"))
    return render_template(
        "admin_leads.html",
        leads=db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall(),
        s=settings(),
        pagina="leads",
    )


@app.route("/admin/senha", methods=["GET", "POST"])
@login_required
def admin_senha():
    if request.method == "POST":
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        conf = request.form.get("confirmar", "")
        db = get_db()
        row = db.execute("SELECT * FROM admins WHERE usuario=?", (session["admin"],)).fetchone()
        if not check_password_hash(row["senha"], atual):
            flash("A senha atual está incorreta.", "erro")
        elif len(nova) < 6:
            flash("A nova senha deve ter pelo menos 6 caracteres.", "erro")
        elif nova != conf:
            flash("A confirmação não coincide com a nova senha.", "erro")
        else:
            db.execute("UPDATE admins SET senha=? WHERE id=?", (generate_password_hash(nova), row["id"]))
            db.commit()
            flash("Senha alterada com sucesso.", "ok")
            return redirect(url_for("admin_senha"))
    return render_template("admin_senha.html", s=settings(), pagina="senha")


os.makedirs(UPLOAD_DIR, exist_ok=True)
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
