# -*- coding: utf-8 -*-
"""El chat: que se acuerde de lo hablado, y que eso no encarezca cada pregunta.

EL CASO. Hasta el 2026-09-27 cada pregunta partia de cero: se mandaba un solo mensaje con todo el
contexto de negocio y la pregunta. Funcionaba para preguntas sueltas y fallaba en cuanto la
conversacion era una conversacion: un "y eso cuanto es" no tenia a que referirse.

Anadir historial es facil de hacer mal de tres formas, y las tres cuestan dinero o una peticion
rota:

1. Mandar la conversacion entera, que multiplica el coste sin mejorar la respuesta.
2. Mandar dos mensajes seguidos del mismo lado, que la API RECHAZA. Pasa de verdad cuando una
   respuesta falla y en pantalla quedan dos burbujas tuyas seguidas.
3. Poner el contexto de negocio al principio de la conversacion en vez de con la ultima pregunta:
   las cifras cambian mientras se habla.

Puros: sin red. La llamada a la API se sustituye.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import chat                              # noqa: E402


# ---------------------------------------------------------------- el historial

def test_dos_mensajes_seguidos_del_mismo_lado_no_revientan_la_peticion():
    """LA API LOS RECHAZA, y pasa de verdad: si una respuesta fallo, en la pantalla quedan dos
    burbujas tuyas seguidas. Sin limpiarlas, la siguiente pregunta fallaria entera con un error que
    no dice nada sobre la causa."""
    h = chat._historial([{"de": "yo", "texto": "una"}, {"de": "yo", "texto": "dos"},
                         {"de": "zeno", "texto": "respuesta"}])
    lados = [m["role"] for m in h]
    assert lados == ["user", "assistant"], lados
    assert h[0]["content"] == "dos", "de dos seguidas se queda la ultima, que es la vigente"


def test_el_historial_empieza_siempre_por_el_usuario():
    """Si el recorte deja arriba una respuesta suelta, la API la rechaza."""
    h = chat._historial([{"de": "zeno", "texto": "cola de antes"}, {"de": "yo", "texto": "hola"}])
    assert h[0]["role"] == "user"


def test_solo_viajan_los_ultimos_turnos():
    """Mandar la conversacion entera encarece cada pregunta sin mejorar la respuesta: el contexto de
    negocio ya va delante completo."""
    largos = [{"de": "yo" if i % 2 == 0 else "zeno", "texto": f"t{i}"} for i in range(30)]
    assert len(chat._historial(largos)) <= chat.TURNOS


def test_cada_turno_se_recorta():
    """Una respuesta larga repetida en las tres preguntas siguientes triplica el coste."""
    h = chat._historial([{"de": "yo", "texto": "x" * 5000}])
    assert len(h[0]["content"]) == chat.LARGO_TURNO


def test_los_turnos_vacios_no_ocupan_sitio():
    assert chat._historial([{"de": "yo", "texto": "   "}, {"de": "yo", "texto": "algo"}]) == [
        {"role": "user", "content": "algo"}]
    assert chat._historial(None) == []


def test_el_contexto_va_con_la_ULTIMA_pregunta_no_al_principio(monkeypatch):
    """Las cifras cambian mientras se habla. Si el contexto fuera el primer mensaje de la
    conversacion, a la tercera pregunta Zeno contestaria con los datos de hace diez minutos sin
    saber que estan viejos."""
    import json as _json
    enviado = {}

    class Falsa:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return _json.dumps({"content": [{"type": "text", "text": "ok"}],
                                "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()

    def falso_urlopen(req, timeout=0):
        enviado.update(_json.loads(req.data))
        return Falsa()

    monkeypatch.setattr(chat, "CLAVE_ANTHROPIC", "k")
    monkeypatch.setattr(chat.urllib.request, "urlopen", falso_urlopen)
    chat.responde("y eso cuanto es", [], [], [], [],
                  turnos=[{"de": "yo", "texto": "como van las ventas"},
                          {"de": "zeno", "texto": "cero"}])
    mensajes = enviado["messages"]
    assert len(mensajes) == 3
    assert mensajes[-1]["role"] == "user"
    assert "PREGUNTA: y eso cuanto es" in mensajes[-1]["content"]
    assert "LO PENDIENTE" in mensajes[-1]["content"] or "sin datos" in mensajes[-1]["content"]
    # Y en los turnos viejos NO va el contexto: repetirlo en cada uno multiplicaria el coste.
    assert "PREGUNTA:" not in mensajes[0]["content"]


def test_el_prompt_prohibe_recalcular_lo_que_ya_viene_dado():
    """PASO DE VERDAD el 2026-09-27, en la primera conversacion con memoria. Con "Caja: $1,150",
    "Beneficio/mes: $-99" y "Runway: 11 meses" delante, la respuesta fue que ese dinero "cubre poco
    mas de una semana", contradiciendo en la misma frase el runway que tenia escrito.

    Un prompt no garantiza nada, asi que esto no prueba que el modelo obedezca: prueba que la regla
    sigue estando. La otra mitad, que la cuenta se escriba cuando se hace, es lo que permite
    pillarlo de un vistazo la proxima vez.
    """
    for regla in ("no lo recalcules", "ESCRIBE la operacion", "El dato manda sobre"):
        assert regla in chat.SISTEMA, f"falta la regla: {regla}"
    assert "no lo recalcules" in chat.SISTEMA_MANANA
