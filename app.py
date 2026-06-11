import streamlit as st
import requests
import json
import os
import uuid
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN DE PÁGINA Y BASE DE DATOS ---
st.set_page_config(page_title="Asistente EIC UCN", page_icon="🎓", layout="wide")

st.markdown("""
    <style>
        .block-container {
            padding-top: 3.5rem;
            padding-bottom: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# ---> TUS LLAVES AQUÍ <---
# ---> YA NO COLOCAMOS LAS LLAVES AQUÍ, LAS LEEMOS DE LOS SECRETS <---
DIFY_API_KEY = st.secrets["DIFY_API_KEY"]
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inicializar memoria
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None
if "usuario_nombre" not in st.session_state:
    st.session_state.usuario_nombre = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = ""
if "calificaciones_guardadas" not in st.session_state:
    st.session_state.calificaciones_guardadas = {}
if "session_uuid" not in st.session_state:
    st.session_state.session_uuid = str(uuid.uuid4()) # Crea un ID único irrepetible

# --- CREACIÓN AUTOMÁTICA DEL USUARIO ANÓNIMO ---
if "anon_user_id" not in st.session_state:
    try:
        # Busca si ya existe la cuenta genérica
        resp = supabase.table("usuarios").select("id").eq("correo", "anonimo@ucn.cl").execute()
        if len(resp.data) > 0:
            st.session_state.anon_user_id = resp.data[0]['id']
        else:
            # Si no existe, la crea
            nuevo_anon = {"correo": "anonimo@ucn.cl", "nombre": "Estudiante Anónimo", "contrasena": "anonimo123"}
            resp_insert = supabase.table("usuarios").insert(nuevo_anon).execute()
            st.session_state.anon_user_id = resp_insert.data[0]['id']
    except Exception as e:
        st.session_state.anon_user_id = None

# --- 2. BARRA LATERAL (SISTEMA DE LOGIN OPCIONAL) ---
with st.sidebar:
    st.markdown("### 🔐 Área del Estudiante")
    
    # --- SI NO HA INICIADO SESIÓN ---
    if not st.session_state.usuario_id:
        st.info("💡 El chat es de uso libre. Inicia sesión solo si deseas guardar tu historial de preguntas.")
        
        tab_login, tab_registro = st.tabs(["Iniciar Sesión", "Registrarse"])
        
        with tab_login:
            correo_login = st.text_input("Correo institucional:", key="login_correo")
            pass_login = st.text_input("Contraseña:", type="password", key="login_pass")
            
            if st.button("Ingresar", type="primary", use_container_width=True):
                if correo_login and pass_login:
                    try:
                        resp = supabase.table("usuarios").select("*").eq("correo", correo_login).eq("contrasena", pass_login).execute()
                        
                        if len(resp.data) > 0:
                            st.session_state.usuario_id = resp.data[0]['id']
                            st.session_state.usuario_nombre = resp.data[0]['nombre']
                            
                            historial = supabase.table("interacciones").select("*").eq("usuario_id", st.session_state.usuario_id).order("fecha").execute()
                            st.session_state.messages = []
                            
                            for fila in historial.data:
                                st.session_state.messages.append({"role": "user", "content": fila["pregunta"]})
                                db_id = fila["id"]
                                st.session_state.messages.append({"role": "assistant", "content": fila["respuesta"], "db_id": db_id})
                                
                                # Restaurar estado de estrellas al iniciar sesión
                                calificacion_bd = fila.get("calificacion")
                                if calificacion_bd is not None:
                                    st.session_state[f"stars_{db_id}"] = calificacion_bd - 1
                                    st.session_state.calificaciones_guardadas[db_id] = calificacion_bd

                            st.success(f"¡Hola, {st.session_state.usuario_nombre}!")
                            st.rerun()
                        else:
                            st.error("Correo o contraseña incorrectos.")
                    except Exception as e:
                        st.error("Error al conectar con la base de datos.")
                else:
                    st.warning("Completa ambos campos.")

        with tab_registro:
            nombre_reg = st.text_input("Tu Nombre Completo:", key="reg_nombre")
            correo_reg = st.text_input("Correo institucional:", key="reg_correo")
            pass_reg = st.text_input("Crea una contraseña:", type="password", key="reg_pass")
            
            if st.button("Crear Cuenta", use_container_width=True):
                if nombre_reg and correo_reg and pass_reg:
                    try:
                        check = supabase.table("usuarios").select("id").eq("correo", correo_reg).execute()
                        if len(check.data) > 0:
                            st.warning("Este correo ya está registrado. Ve a Iniciar Sesión.")
                        else:
                            nuevo_user = {"correo": correo_reg, "contrasena": pass_reg, "nombre": nombre_reg}
                            supabase.table("usuarios").insert(nuevo_user).execute()
                            st.success("¡Cuenta creada! Ahora ve a 'Iniciar Sesión' para entrar.")
                    except Exception as e:
                        st.error("Error al crear la cuenta.")
                else:
                    st.warning("Debes completar todos los campos.")
                    
    # --- SI YA INICIÓ SESIÓN ---
    else:
        st.success(f"Conectado como: {st.session_state.usuario_nombre}")
        
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.usuario_id = None
            st.session_state.usuario_nombre = None
            st.session_state.messages = []
            st.session_state.conversation_id = ""
            st.rerun()
            
        st.divider()
        st.markdown("### 📝 ¿Terminaste?")
        
        with st.form("encuesta_form"):
            resolvio = st.selectbox("¿Resolviste tu duda principal?", ["Sí", "Parcialmente", "No"])
            comentarios = st.text_area("Déjanos un comentario o sugerencia:")
            submit_encuesta = st.form_submit_button("Enviar respuestas")
            
            if submit_encuesta:
                try:
                    datos_encuesta = {
                        "usuario_id": st.session_state.usuario_id,
                        "resolvio_duda": resolvio,
                        "comentario": comentarios
                    }
                    supabase.table("encuestas_salida").insert(datos_encuesta).execute()
                    st.success("¡Gracias por tu feedback!")
                except Exception as e:
                    st.error("Error al guardar la encuesta.")


# --- 3. DISEÑO DEL ENCABEZADO ---
col1, col2, col3 = st.columns([1, 4, 1])

with col1:
    if os.path.exists("logo_ucn.png"):
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.image("logo_ucn.png", width=120) 
    else:
        st.caption("🖼️ logo_ucn.png")

with col2:
    st.markdown("<h2 style='text-align: center; color: #00b4c8; margin: 0; padding-top: 25px;'>Asistente Virtual EIC</h2>", unsafe_allow_html=True)

with col3:
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    if os.path.exists("logo_eic.png"):
        st.image("logo_eic.png", width=140) 
    elif os.path.exists("logo_eic.svg"):
        st.image("logo_eic.svg", width=140)
    else:
        st.caption("🖼️ logo_eic")

st.markdown("<p style='text-align: center; color: #e0e0e0; margin-top: 10px;'>Consulta normativas, plazos y el reglamento de la Escuela de Ingeniería.</p>", unsafe_allow_html=True)
st.divider()

# --- 4. LÓGICA DEL CHAT Y FEEDBACK ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Validamos que sea del asistente Y que tenga un db_id válido para no romper la app
        if msg["role"] == "assistant":
            db_id = msg.get("db_id")
            
            if db_id is not None:
                # ---> NUEVO: Mensaje explicativo sobre las estrellas <---
                st.caption("¿Qué te pareció esta respuesta?")
                calificacion = st.feedback("stars", key=f"stars_{db_id}")
                
                if calificacion is not None:
                    estrellas = calificacion + 1
                    if st.session_state.calificaciones_guardadas.get(db_id) != estrellas:
                        try:
                            supabase.table("interacciones").update({"calificacion": estrellas}).eq("id", db_id).execute()
                            st.session_state.calificaciones_guardadas[db_id] = estrellas
                            st.toast(f"¡Gracias! Calificaste con {estrellas} estrellas ⭐")
                        except Exception as e:
                            st.error("Error al guardar calificación.")

user_input = st.chat_input("Escribe tu duda aquí (ej. ¿Cuándo inician las clases?)...")

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": {},
        "query": user_input,
        "response_mode": "streaming", 
        "conversation_id": st.session_state.conversation_id,
        "user": str(st.session_state.usuario_id) if st.session_state.usuario_id else "estudiante_anonimo"
    }

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            response = requests.post(DIFY_API_URL, headers=headers, json=payload, stream=True)
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data: "):
                            data_str = decoded_line[6:]
                            try:
                                data = json.loads(data_str)
                                event = data.get("event")

                                if event == "message":
                                    chunk = data.get("answer", "")
                                    full_response += chunk
                                    message_placeholder.markdown(full_response + "▌")
                                
                                elif event == "message_end":
                                    st.session_state.conversation_id = data.get("conversation_id", "")
                            except json.JSONDecodeError:
                                pass
                
                message_placeholder.markdown(full_response)
                
                # Guardado seguro con manejo de errores
                nuevo_id = None
                try:
                    user_id_to_save = st.session_state.usuario_id if st.session_state.usuario_id else st.session_state.anon_user_id
                    
                    datos_insercion = {
                        "conversacion_id": st.session_state.conversation_id,
                        "pregunta": user_input,
                        "respuesta": full_response,
                        "usuario_id": user_id_to_save
                    }
                    
                    respuesta_db = supabase.table("interacciones").insert(datos_insercion).execute()
                    
                    if respuesta_db.data and len(respuesta_db.data) > 0:
                        nuevo_id = respuesta_db.data[0]['id']
                    else:
                        st.toast("Aviso: La base de datos no devolvió un ID válido.")
                        
                except Exception as e:
                    st.error(f"Error al guardar en BD: {e}")

                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_response,
                    "db_id": nuevo_id
                })
                st.rerun()

            else:
                st.error(f"Error en el servidor: {response.status_code}")
                
        except Exception as e:
            st.error(f"Error de conexión: {e}")