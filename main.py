from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random, string, threading, time, os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Estructura de partidas
# {codigo: {"jugadores":{nombre:estado}, "fotos":{nombre:url}, "roles_descartados":[], "votacion":None}}
partidas = {}
# ---- ROLES (pool fijo de 15) ----
ROLES_BUEN_CIUDADANO = [
    "demonio", "rey", "adivina", "monja", "guerrero", "tonto del pueblo", "bruja"
]
ROLES_CIUDADANO = [
    "jacob", "ramera", "cazador", "boticario", "celestina", "asesino"
]
ROL_DOCTOR = ["doctor peste"]
ROL_HIJO = ["hijo del doctor"]

ROLES_BASE = ROL_DOCTOR + ROL_HIJO + ROLES_BUEN_CIUDADANO + ROLES_CIUDADANO
# (Total = 1 + 1 + 7 + 6 = 15)

# Reglas de roles según número de jugadores

# -----------------------------------
# RUTAS
# -----------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/nueva")
def nueva():
    codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    partidas[codigo] = {"jugadores": {}, "fotos": {}, "roles_descartados": [], "votacion": None}
    return render_template("nueva.html", codigo=codigo)

@app.route("/unirse_form")
def unirse_form():
    return render_template("unirse.html")

@app.route("/sala/<codigo>/<nombre>")
def sala(codigo, nombre):
    es_host = nombre == "HOST"
    return render_template("sala.html", codigo=codigo, nombre=nombre, es_host=es_host)

# -----------------------------------
# SOCKETS
# -----------------------------------
@socketio.on("join")
def join(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    join_room(codigo)
    if codigo in partidas:
        if nombre in partidas[codigo]["jugadores"]:
            if partidas[codigo]["jugadores"][nombre] == "inactivo":
                partidas[codigo]["jugadores"][nombre] = "activo"
        emit("jugadores", {
            "jugadores": partidas[codigo]["jugadores"],
            "fotos": partidas[codigo]["fotos"]
        }, to=codigo)
        emit("roles_descartados", partidas[codigo]["roles_descartados"], to=codigo)

@socketio.on("unirse_con_foto")
def unirse_con_foto(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    foto = data["foto"]
    join_room(codigo)
    if codigo in partidas:
        if nombre in partidas[codigo]["jugadores"]:
            if partidas[codigo]["jugadores"][nombre] == "inactivo":
                partidas[codigo]["jugadores"][nombre] = "activo"
        else:
            partidas[codigo]["jugadores"][nombre] = "activo"
            partidas[codigo]["fotos"][nombre] = foto
    emit("jugadores", {
        "jugadores": partidas[codigo]["jugadores"],
        "fotos": partidas[codigo]["fotos"]
    }, to=codigo)
    emit("roles_descartados", partidas[codigo]["roles_descartados"], to=codigo)

@socketio.on("set_status")
def set_status(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    status = "activo" if data["status"] else "inactivo"
    if nombre in partidas[codigo]["jugadores"]:
        if partidas[codigo]["jugadores"][nombre] != "muerto":
            partidas[codigo]["jugadores"][nombre] = status
        emit("jugadores", {
            "jugadores": partidas[codigo]["jugadores"],
            "fotos": partidas[codigo]["fotos"]
        }, to=codigo)

# -----------------------------------
# DESCARTAR ROLES
# -----------------------------------
import random
from flask import request

REGLAS = {
    5:  {"buen_ciudadano":2, "ciudadano":2, "doctor":1, "hijo":0},
    6:  {"buen_ciudadano":3, "ciudadano":2, "doctor":1, "hijo":0},
    7:  {"buen_ciudadano":3, "ciudadano":3, "doctor":1, "hijo":0},
    8:  {"buen_ciudadano":3, "ciudadano":3, "doctor":1, "hijo":1},
    9:  {"buen_ciudadano":4, "ciudadano":3, "doctor":1, "hijo":1},
    10: {"buen_ciudadano":4, "ciudadano":4, "doctor":1, "hijo":1},
    11: {"buen_ciudadano":4, "ciudadano":4, "doctor":1, "hijo":1},
    12: {"buen_ciudadano":5, "ciudadano":5, "doctor":1, "hijo":1}
}

@socketio.on("asignar_roles")
def asignar_roles(data):
    codigo = data["codigo"]
    if codigo not in partidas:
        emit("error", "Partida no encontrada", to=request.sid)
        return

    # Solo el host debe poder pulsar el botón (opcional: compruébalo si quieres)
    # host = data.get("host")

    n_jugadores = len(partidas[codigo]["jugadores"])
    if n_jugadores not in REGLAS:
        emit("error", f"Número de jugadores {n_jugadores} no soportado", to=request.sid)
        return

    r = REGLAS[n_jugadores]

    # 1) Selección por categorías con nombres reales
    # Buen ciudadano
    if r["buen_ciudadano"] > len(ROLES_BUEN_CIUDADANO):
        emit("error", "No hay suficientes roles de buen ciudadano en el pool", to=request.sid)
        return
    buenos = random.sample(ROLES_BUEN_CIUDADANO, r["buen_ciudadano"])

    # Ciudadano
    if r["ciudadano"] > len(ROLES_CIUDADANO):
        emit("error", "No hay suficientes roles de ciudadano en el pool", to=request.sid)
        return
    ciudadanos = random.sample(ROLES_CIUDADANO, r["ciudadano"])

    # Doctor peste (siempre 1 según reglas)
    doctor = ROL_DOCTOR if r["doctor"] == 1 else []

    # Hijo del doctor (0 o 1)
    hijo = ROL_HIJO if r["hijo"] == 1 else []

    roles_uso = doctor + hijo + buenos + ciudadanos
    random.shuffle(roles_uso)  # mezclar para no revelar composición

    # 2) Descartados = todos los 15 menos los que se usan
    roles_descartados = ROLES_BASE.copy()
    for rol in roles_uso:
        # quitar una instancia exacta del rol usado
        if rol in roles_descartados:
            roles_descartados.remove(rol)

    # Guardar en memoria y emitir
    partidas[codigo]["roles_descartados"] = roles_descartados
    partidas[codigo]["roles_usados"] = roles_uso  # por si el host los necesita

    # Visible para TODOS: los que NO juegan esta partida
    emit("roles_descartados", roles_descartados, to=codigo)

    # Opcional: enviar SOLO al host los que sí juegan (si tu frontend lo usa)
    emit("roles_no_descartados", roles_uso, to=request.sid)



# -----------------------------------
# MATAR JUGADOR
# -----------------------------------
@socketio.on("matar_jugador")
def matar_jugador(data):
    codigo = data["codigo"]
    jugador = data["jugador"]
    partidas[codigo]["jugadores"][jugador] = "muerto"
    emit("jugadores", {
        "jugadores": partidas[codigo]["jugadores"],
        "fotos": partidas[codigo]["fotos"]
    }, to=codigo)

# -----------------------------------
# VOTACION
# -----------------------------------
@socketio.on("iniciar_hoguera")
def iniciar_hoguera(data):
    codigo = data["codigo"]
    tiempo = int(data["tiempo"])
    if partidas[codigo]["votacion"]:
        return
    votacion = {
        "tiempo_restante": tiempo,
        "votos": {},
        "jugadores_vivos": [j for j,s in partidas[codigo]["jugadores"].items() if s!="muerto"],
        "finalizada": False
    }
    partidas[codigo]["votacion"] = votacion
    threading.Thread(target=timer_votacion, args=(codigo,)).start()
    for j in votacion["jugadores_vivos"]:
        emit("votacion_iniciada", {"jugadores": votacion["jugadores_vivos"], "tiempo": tiempo, "ya_voto": j in votacion["votos"]}, room=codigo)

def timer_votacion(codigo):
    while partidas[codigo]["votacion"]["tiempo_restante"] > 0:
        time.sleep(1)
        partidas[codigo]["votacion"]["tiempo_restante"] -= 1
        socketio.emit("votacion_tick", partidas[codigo]["votacion"]["tiempo_restante"], to=codigo)
        if len(partidas[codigo]["votacion"]["votos"]) == len([j for j,s in partidas[codigo]["jugadores"].items() if s!="muerto"]):
            break
    finalizar_votacion(codigo)

def finalizar_votacion(codigo):
    votacion = partidas[codigo]["votacion"]
    if votacion["finalizada"]:
        return
    votacion["finalizada"] = True
    resultados = {}
    for voto in votacion["votos"].values():
        resultados[voto] = resultados.get(voto,0)+1
    socketio.emit("votacion_finalizada", resultados, to=codigo)
    partidas[codigo]["votacion"] = None

@socketio.on("votar")
def votar(data):
    codigo = data["codigo"]
    votante = data["votante"]
    voto = data["voto"]
    votacion = partidas[codigo]["votacion"]
    if votacion and votante in votacion["jugadores_vivos"] and votante not in votacion["votos"]:
        votacion["votos"][votante] = voto
        emit("votacion_iniciada", {"jugadores": votacion["jugadores_vivos"], "tiempo": votacion["tiempo_restante"], "ya_voto": True}, room=request.sid)

# -----------------------------------
# RUN
# -----------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    socketio.run(app, host="0.0.0.0", port=port)
