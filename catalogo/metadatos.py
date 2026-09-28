# -*- coding: utf-8 -*-
"""El contrato de cada una de las 33 acciones, indexado por la clave del recolector.

Medido y declarado el 2026-09-27. La clave la produce `recolector.clave()`:
`sistema|verbo|destino|cuerpo|etiqueta`. Se escribe entera y no por trozos para que un cambio en
cualquiera de sus partes (que cambie el destino, que cambie la etiqueta) rompa el test en vez de
emparejar en silencio la accion equivocada con el contrato equivocado.

`guarda` dice lo que protege la accion HOY. Donde pone "ninguna" es un dato y no un olvido: son las
que el asistente tiene que confirmar siempre, porque nada mas lo va a hacer.
"""
from .contrato import ABRE, CAMBIA_ESTADO, PUBLICA, Contrato

CONTRATOS: dict[str, Contrato] = {

    # ---------------- El trabajo del dia: outreach de LinkedIn y engagement de X ----------------
    #
    # Declaradas el 2026-09-28, cuando el operador pidio poder marcarlas desde el movil sin abrir
    # el cockpit. Las cinco COMPARTEN una cosa que las hace seguras: el mensaje se escribe y se
    # manda EN LinkedIn o EN X, a mano. Ninguna de estas manda nada a nadie: solo anotan en que
    # punto esta cada prospecto o cada cuenta.
    #
    # Por eso ninguna es `publica` aunque hablen de mensajes enviados: lo que ya salio, salio, y
    # esto es el cuaderno donde se apunta.
    "cockpit|POST|/marketing/linkedin/{pid}/mark-contacted||✓ Nota enviada": Contrato(
        op="dm.nota_enviada",
        que_hace="Anota que ya se mando la solicitud de conexion con su nota, a mano en LinkedIn",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="consume cuota del dia (15): el propio cockpit deja de ofrecer mas cuando se agota"),
    "cockpit|POST|/marketing/linkedin/{pid}/connected||🤝 Conectó": Contrato(
        op="dm.acepto",
        que_hace="Anota que el prospecto acepto la conexion, y arranca su arco a los dos dias",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="no escribe a nadie: el primer mensaje del arco aparece dos dias despues"),
    "cockpit|PATCH|/marketing/linkedin/{pid}/arc|arc_stage=0|✓ Mensaje enviado": Contrato(
        op="dm.avanzar_arco",
        que_hace="Anota hasta que mensaje del arco se ha enviado, y programa el siguiente",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="tope de 15 avances al dia; el mensaje se copia y se pega en LinkedIn a mano"),
    # Cerrar una respuesta ya atendida. Dos claves porque hay dos caminos: con arco se avanza
    # (el sistema sabe asi que le contestaste), y sin arco se esconde el aviso. Ninguna manda
    # nada: contestar se hace EN LinkedIn.
    "cockpit|PATCH|/marketing/linkedin/{pid}/arc|arc_stage=<dinamico>|✓ Ya le he contestado": Contrato(
        op="dm.respuesta_atendida",
        que_hace="Anota que ya se contesto a quien habia escrito, y programa el siguiente paso",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="no escribe a nadie: la respuesta se manda a mano en LinkedIn"),
    "cockpit|POST|/notifications/dismiss|item_id=reply:{pid}|✓ Ya le he contestado": Contrato(
        op="aviso.esconder",
        que_hace="Esconde el aviso de una respuesta ya atendida cuando no hay arco que avanzar",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="no borra a nadie ni cambia su estado: vuelve a salir si el de debajo cambia"),
    "cockpit|POST|/marketing/x-targets/{tid}/mark-engaged||✓ Respondí": Contrato(
        op="x.ya_respondi",
        que_hace="Anota que ya se respondio a esa cuenta hoy, y sale del recordatorio",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="no escribe en X: el comentario se publica alli a mano"),
    "cockpit|POST|/marketing/x-targets/{tid}/skip-today||⤫ Saltar hoy": Contrato(
        op="x.saltar_hoy",
        que_hace="Esconde esa cuenta hasta mañana sin contarla como respondida",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="ninguna, y no hace falta: vuelve a salir mañana"),

    # ---------------- COCKPIT, lo que sale al mundo ----------------
    "cockpit|GET|{N8N_PUBLIC}/webhook/linkedin-approve?id={pid}||✅ Aprobar": Contrato(
        op="linkedin.aprobar_y_publicar",
        que_hace="Aprueba el post de LinkedIn y lo PUBLICA en el momento",
        efecto=PUBLICA, reversible=False,
        guarda="aprobar es publicar (regla del operador): no hay paso intermedio ni vuelta atras"),
    "cockpit|GET|{N8N_PUBLIC}/webhook/linkedin-regenerate?id={pid}||\U0001f504 Regenerar": Contrato(
        op="linkedin.regenerar",
        que_hace="Descarta el texto y pide otro a Claude para el mismo tema",
        efecto=CAMBIA_ESTADO, reversible=False, coste_api=True,
        guarda="ninguna: gasta una llamada de pago cada vez que se pulsa"),
    "cockpit|GET|{N8N_PUBLIC}/webhook/newsletter-confirm?nl_id={nl}&action=mark_published||\U0001f4f0 Publicar / confirmar": Contrato(
        op="newsletter.confirmar_publicada",
        que_hace="Marca la newsletter como publicada en LinkedIn y cierra su hueco en la cola",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="tope de 12 en la cola de newsletters"),
    "cockpit|POST|/marketing/content-x/{pid}/publish||▲ Publicar en X": Contrato(
        op="x.publicar",
        que_hace="Publica el tweet y su respuesta con el enlace, por la API de X",
        efecto=PUBLICA, reversible=False,
        guarda="exige cuenta de X conectada; si no lo esta, falla en vez de perder el texto"),
    "cockpit|POST|/marketing/magnet-promo/{pid}/publish||▲ Publicar en LinkedIn": Contrato(
        op="magnet.publicar_en_linkedin",
        que_hace="Publica en LinkedIn el post que promociona un magnet",
        efecto=PUBLICA, reversible=False,
        guarda="el enlace del magnet lleva el idioma del post (regla medida en septiembre)"),
    "cockpit|POST|/newsletter/letters/{slug}/send||✅ Aprobar y enviar": Contrato(
        op="carta.aprobar_y_enviar",
        que_hace="Envia la Automation Letter a su lista de suscriptores",
        efecto=PUBLICA, reversible=False,
        guarda="ninguna en la accion: el correo sale al pulsar"),

    # ---------------- COCKPIT, estado interno ----------------
    "cockpit|POST|/marketing/content-x/{pid}/status|x_status=posted|✅ Marcar publicado a mano": Contrato(
        op="x.marcar_publicado",
        que_hace="Anota que ese tweet ya se publico a mano, sin llamar a X",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="ninguna: es una anotacion, y marcarla por error deja el post sin publicar de verdad"),
    "cockpit|PATCH|/marketing/topics/{pid}|status=published|✅ Marcar publicado": Contrato(
        op="tema.marcar_publicado",
        que_hace="Cierra el tema del pool como ya publicado",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="el guard anti-duplicado del pool usa este estado para no regenerar lo ya publicado"),
    "cockpit|PATCH|/marketing/magnet-promo/{pid}|publication_status=cancelled|✕ Cancelar": Contrato(
        op="magnet.cancelar_publicacion",
        que_hace="Cancela la publicacion prevista del post de magnet en LinkedIn",
        efecto=CAMBIA_ESTADO, reversible=True, guarda="ninguna"),
    "cockpit|PATCH|/marketing/magnet-promo/{pid}|x_status=posted|✅ Marcar publicado": Contrato(
        op="magnet.marcar_publicado_en_x",
        que_hace="Anota que el hilo de X del magnet ya salio",
        efecto=CAMBIA_ESTADO, reversible=True, guarda="ninguna"),
    "cockpit|PATCH|/marketing/magnet-promo/{pid}|x_status=cancelled|✕ Descartar thread": Contrato(
        op="magnet.descartar_hilo_x",
        que_hace="Descarta el hilo de X del magnet sin publicarlo",
        efecto=CAMBIA_ESTADO, reversible=True, guarda="ninguna"),
    "cockpit|PATCH|/marketing/newsletter/{nid}|scheduled_in_li=True|✅ Ya está programado": Contrato(
        op="newsletter.marcar_programada",
        que_hace="Anota que la newsletter ya esta programada en LinkedIn",
        efecto=CAMBIA_ESTADO, reversible=True, guarda="tope de 12 en la cola de newsletters"),

    # ---------------- COCKPIT, solo abren ----------------
    "cockpit|GET|/marketing?open={pid}&src=pool||\U0001f440 Revisar y publicar": Contrato(
        op="abrir.post_del_pool", que_hace="Abre el post en Marketing para revisarlo",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|/marketing/x?open={pid}||\U0001f50d Revisar / copiar": Contrato(
        op="abrir.tweet", que_hace="Abre el tweet en la pantalla de X",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|/marketing/magnets||\U0001f50d Revisar": Contrato(
        op="abrir.magnets", que_hace="Abre la pantalla de magnets",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|/marketing/magnets||\U0001f50d Revisar y copiar": Contrato(
        op="abrir.magnets_para_copiar", que_hace="Abre la pantalla de magnets para copiar el texto",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|/marketing/distribucion||Abrir la preparación": Contrato(
        op="abrir.distribucion_preparacion",
        que_hace="Abre la preparacion de la distribucion en directorios",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|/marketing/distribucion||Abrir el panel": Contrato(
        op="abrir.distribucion_panel", que_hace="Abre el panel de distribucion",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|<dinamico>||\U0001f441️ Ver la carta": Contrato(
        op="abrir.carta", que_hace="Abre la Automation Letter para leerla antes de enviarla",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|<dinamico>||\U0001f4cb Abrir guía de montaje": Contrato(
        op="abrir.guia_montaje", que_hace="Abre la guia de montaje del video",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|https://magnets.zenvrax.com/distribucion/estado.html||Qué falta por producto": Contrato(
        op="abrir.estado_distribucion",
        que_hace="Abre la pagina de estado de la distribucion por producto",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|https://magnets.zenvrax.com/distribucion/estado.html||Qué falta y por dónde se retoma": Contrato(
        op="abrir.estado_distribucion_retomar",
        que_hace="Abre el estado de la distribucion indicando por donde se retoma",
        efecto=ABRE, reversible=True, confirmar=False),
    "cockpit|GET|https://magnets.zenvrax.com/xsupport/alta/guia.html||Guía de envío": Contrato(
        op="abrir.guia_envio_xsupport", que_hace="Abre la guia de envio del alta de XSupport",
        efecto=ABRE, reversible=True, confirmar=False),

    # ---------------- XRISE (GutLyn) ----------------
    "xrise|POST|/content/claire/{pid}/action|action=publish|✅ Aprobar y publicar": Contrato(
        op="claire.aprobar_y_publicar",
        que_hace="Aprueba el post de Claire y lo publica en Instagram y Facebook",
        efecto=PUBLICA, reversible=False,
        guarda="CLAIRE_PUBLISH_TESTING_MODE: si esta activa, publica en seco"),
    "xrise|POST|/content/claire/{pid}/action|action=regenerate|\U0001f504 Regenerar": Contrato(
        op="claire.regenerar", que_hace="Pide a Claire otro texto para el mismo tema",
        efecto=CAMBIA_ESTADO, reversible=False, coste_api=True,
        guarda="ninguna: gasta una llamada de pago por pulsacion"),
    "xrise|POST|/content/claire/{pid}/action|action=drop|⏭️ No postear (posponer)": Contrato(
        op="claire.posponer",
        que_hace="No publica hoy y mueve el post al proximo viernes libre de su cadencia",
        efecto=CAMBIA_ESTADO, reversible=True,
        guarda="no pisa un dia que ya tenga contenido real, mirando las dos fuentes"),
    "xrise|POST|/content/gutlyn/{pid}/action|action=publish|✅ Aprobar y publicar": Contrato(
        op="gutlyn.aprobar_y_publicar",
        que_hace="Aprueba el post organico de GutLyn y lo publica en Meta",
        efecto=PUBLICA, reversible=False, guarda="ninguna"),
    "xrise|POST|/content/gutlyn/{pid}/action|action=regenerate|\U0001f504 Regenerar": Contrato(
        op="gutlyn.regenerar", que_hace="Pide otro texto para el post organico de GutLyn",
        efecto=CAMBIA_ESTADO, reversible=False, coste_api=True,
        guarda="ninguna: gasta una llamada de pago por pulsacion"),
    "xrise|POST|/engagement/comments/{cid}/publish||✅ Aprobar y publicar": Contrato(
        op="engagement.publicar_respuesta",
        que_hace="Publica la respuesta al comentario en la red donde se recibio",
        efecto=PUBLICA, reversible=False,
        guarda="las acciones inteligentes de Xrise exigen el OK del operador (regla)"),
    "xrise|POST|/engagement/comments/{cid}/discard||\U0001f5d1️ Descartar respuesta": Contrato(
        op="engagement.descartar_respuesta",
        que_hace="Descarta la respuesta propuesta sin publicarla",
        efecto=CAMBIA_ESTADO, reversible=True, guarda="ninguna"),
    "xrise|POST|/marketing/reorder/enroll||✅ Lanzar campaña de recompra": Contrato(
        op="recompra.lanzar_campana",
        que_hace="Mete a los clientes que toca en la campana de recompra por correo",
        efecto=PUBLICA, reversible=False,
        guarda="ninguna en la accion: los correos empiezan a salir"),
    "xrise|GET|https://n8n.zenvrax.com/webhook/gutlyn-claire-preview?id={pid}||\U0001f440 Ver preview": Contrato(
        op="abrir.preview_claire", que_hace="Abre la vista previa del post de Claire",
        efecto=ABRE, reversible=True, confirmar=False),
    "xrise|GET|https://n8n.zenvrax.com/webhook/meta-preview?id={pid}||\U0001f440 Ver preview": Contrato(
        op="abrir.preview_gutlyn",
        que_hace="Abre la vista previa del post organico de GutLyn",
        efecto=ABRE, reversible=True, confirmar=False),
}
