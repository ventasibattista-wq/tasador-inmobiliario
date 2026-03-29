import streamlit as st
import requests
import cloudscraper  # <-- NUEVA LIBRERÍA
from bs4 import BeautifulSoup
import time
import statistics
import pandas as pd
import plotly.express as px # <-- Nueva librería gráfica

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AVM Inmobiliario | Panel", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")

# --- DISEÑO CSS CORPORATIVO Y ADAPTABLE ---
st.markdown("""
    <style>
    .stApp { background-color: #F8FAFC; }
    .titulo-app { font-size: 2.2rem; font-weight: 800; color: #0F172A; margin-bottom: 0px; padding-bottom: 0px; letter-spacing: -0.5px; }
    .subtitulo-app { font-size: 1rem; color: #64748B; margin-bottom: 25px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; }
    div[data-testid="metric-container"] { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 20px 25px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06); border-top: 4px solid #1E3A8A; }
    div[data-testid="stMetricLabel"] { font-size: 0.9rem !important; color: #64748B !important; font-weight: 600; }
    div[data-testid="stMetricValue"] { font-size: 2rem !important; color: #0F172A !important; font-weight: 700; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    @media (max-width: 768px) {
        .titulo-app { font-size: 1.6rem; }
        .subtitulo-app { font-size: 0.8rem; margin-bottom: 15px; }
        div[data-testid="metric-container"] { padding: 15px 15px; }
        div[data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIONES DE EXTRACCIÓN (Vía ScraperAPI) ---
@st.cache_data(show_spinner=False) 
def obtener_links_del_listado(url_listado):
    # Traemos tu clave secreta desde la configuración de Streamlit
    API_KEY = st.secrets["SCRAPER_API_KEY"]
    
    # Preparamos la orden para el testaferro digital
    payload = {'api_key': API_KEY, 'url': url_listado, 'country_code': 'ar'}
    
    try:
        respuesta = requests.get('http://api.scraperapi.com', params=payload)
        if respuesta.status_code != 200:
            return []
            
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        tarjetas = soup.find_all('li', class_='ui-search-layout__item')
        links = []
        for tarjeta in tarjetas:
            link_elemento = tarjeta.find('a', href=True)
            if link_elemento:
                link_encontrado = link_elemento['href']
                if "alquiler" not in link_encontrado.lower():
                    links.append(link_encontrado)
        return links
    except:
        return []

def extraer_detalle_propiedad(url_propiedad):
    API_KEY = st.secrets["SCRAPER_API_KEY"]
    payload = {'api_key': API_KEY, 'url': url_propiedad, 'country_code': 'ar'}
    
    try:
        respuesta = requests.get('http://api.scraperapi.com', params=payload)
        if respuesta.status_code != 200:
            return None
            
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        titulo_el = soup.find('h1', class_='ui-pdp-title')
        titulo = titulo_el.text.strip() if titulo_el else "Sin título"
        moneda_el = soup.find('span', class_='andes-money-amount__currency-symbol')
        moneda = moneda_el.text.strip() if moneda_el else ""
        precio_el = soup.find('span', class_='andes-money-amount__fraction')
        precio = precio_el.text.strip() if precio_el else "Sin precio"
        superficie, ambientes, antiguedad = "No especificada", "No especificados", "No especificada"
        filas_tabla = soup.find_all('tr', class_='andes-table__row')
        for fila in filas_tabla:
            encabezado = fila.find('th')
            valor = fila.find('td')
            if encabezado and valor:
                texto = encabezado.text.lower()
                if "superficie total" in texto:
                    superficie = valor.text.strip()
                elif "ambientes" in texto:
                    ambientes = valor.text.strip()
                elif "antigüedad" in texto or "antiguedad" in texto:
                    antiguedad = valor.text.strip()

        precio_limpio = precio.replace(".", "").strip()
        superficie_limpia = superficie.replace(" m²", "").replace(" m2", "").replace(" útil", "").replace(",", ".").strip()
        ambientes_limpios = ambientes.replace(" ambientes", "").replace(" ambiente", "").strip()
        precio_m2 = "No calculable"
        superficie_final = superficie_limpia
        
        try:
            num_precio = float(precio_limpio)
            num_superficie = float(superficie_limpia)
            if num_superficie > 0:
                calculo = num_precio / num_superficie
                precio_m2 = int(round(calculo))
                superficie_final = int(round(num_superficie))
        except ValueError:
            pass

        return {
            "Titulo": titulo,
            "Moneda": moneda,
            "Precio": int(precio_limpio) if precio_limpio.isdigit() else precio_limpio, 
            "Superficie": superficie_final,
            "Ambientes": ambientes_limpios,
            "Antigüedad": antiguedad,
            "Precio_m2": precio_m2,
            "Link": url_propiedad
        }
    except:
        return None

def formato_moneda(numero): return f"{numero:,.0f}".replace(",", ".")

# --- BASE DE DATOS GEOGRÁFICA ---
zonas_y_barrios = {
    "Capital Federal": ["Almagro", "Balvanera", "Belgrano", "Caballito", "Flores", "Nuñez", "Palermo", "Recoleta", "Villa Crespo", "Villa Devoto", "Villa Urquiza"],
    "GBA Oeste": ["Castelar", "Ciudadela", "Haedo", "Ituzaingó", "Morón", "Ramos Mejía", "San Justo"],
    "GBA Norte": ["Martínez", "Olivos", "Pilar", "San Isidro", "Tigre", "Vicente López"],
    "GBA Sur": ["Avellaneda", "Banfield", "Lanús", "Lomas de Zamora", "Quilmes"]
}
mapa_zonas_url = {
    "Capital Federal": "capital-federal", "GBA Oeste": "bsas-gba-oeste", 
    "GBA Norte": "bsas-gba-norte", "GBA Sur": "bsas-gba-sur"
}

# ==========================================
# BARRA LATERAL (PANEL DE CONTROL / FILTROS)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2933/2933245.png", width=60) 
    st.markdown("### Parámetros de Tasación")
    st.markdown("Configure los filtros para la extracción de mercado.")
    st.divider()
    
    zona_elegida = st.selectbox("1. Zona Operativa", list(zonas_y_barrios.keys()))
    barrio_elegido = st.selectbox("2. Localidad", zonas_y_barrios[zona_elegida])
    tipo_elegido = st.selectbox("3. Tipo de Inmueble", ["Departamentos", "Casas", "PH"])
    condicion_elegida = st.selectbox("4. Condición", ["Indistinto", "A estrenar", "Usado"])
    cantidad_analizar = st.slider("5. Tamaño de Muestra", min_value=10, max_value=40, value=20, step=5)
    
    st.divider()
    boton_iniciar = st.button("Ejecutar Análisis", type="primary", use_container_width=True)

# ==========================================
# PANTALLA PRINCIPAL (RESULTADOS)
# ==========================================
st.markdown('<p class="titulo-app">Plataforma de Valoración AVM</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitulo-app">Reporte automatizado de mercado inmobiliario</p>', unsafe_allow_html=True)

if not boton_iniciar:
    st.info("👈 Configure los parámetros en el panel lateral y presione 'Ejecutar Análisis' para comenzar.")

if boton_iniciar:
    tipo_url = tipo_elegido.lower()
    zona_url = mapa_zonas_url[zona_elegida]
    barrio_url = barrio_elegido.lower().replace(" ", "-").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    
    condicion_sufijo = ""
    if condicion_elegida == "A estrenar": condicion_sufijo = "_Condicion_AEstrenar"
    elif condicion_elegida == "Usado": condicion_sufijo = "_Condicion_Usado"
    
    url_buscar = f"https://listado.mercadolibre.com.ar/inmuebles/{tipo_url}/venta/{zona_url}/{barrio_url}/{condicion_sufijo}"
    
    with st.status("Recopilando datos del mercado...", expanded=True) as status:
        st.write(f"Conectando al nodo: {zona_elegida} > {barrio_elegido}")
        links_propiedades = obtener_links_del_listado(url_buscar)
        links_a_procesar = links_propiedades[:cantidad_analizar]
        
        if not links_a_procesar:
            status.update(label="Operación abortada", state="error", expanded=False)
            st.error("La consulta no arrojó resultados válidos. Intente ampliar los parámetros.")
        else:
            resultados = []
            barra_progreso = st.progress(0)
            
            for i, link in enumerate(links_a_procesar, 1):
                st.write(f"Analizando comparable {i}/{len(links_a_procesar)}...")
                datos = extraer_detalle_propiedad(link)
                if datos: resultados.append(datos)
                barra_progreso.progress(i / len(links_a_procesar))
                time.sleep(1)
                
            status.update(label="Análisis finalizado", state="complete", expanded=False)
            
            # Filtramos los datos válidos para la estadística
            datos_validos = [d for d in resultados if d["Precio_m2"] != "No calculable" and d["Moneda"] in ["U$S", "USD", "US$"]]
            precios_m2_validos = [d["Precio_m2"] for d in datos_validos]
            
            if precios_m2_validos:
                mediana_estimada = int(round(statistics.median(precios_m2_validos)))
                promedio_estimado = int(round(statistics.mean(precios_m2_validos)))
                
                # --- MÉTRICAS ---
                st.markdown("### 📈 Resumen de Tasación")
                col1, col2, col3 = st.columns(3)
                col1.metric("Valor Sugerido (Mediana)", f"U$S {formato_moneda(mediana_estimada)}")
                col2.metric("Promedio Aritmético", f"U$S {formato_moneda(promedio_estimado)}")
                col3.metric("Volumen de Muestra", f"{len(precios_m2_validos)} Inmuebles")
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # --- GRÁFICO DE DISPERSIÓN INTERACTIVO ---
                st.markdown("### 🎯 Dispersión del Mercado (U$S/m²)")
                
                # Preparamos el DataFrame solo con los válidos para graficar
                df_grafico = pd.DataFrame(datos_validos)
                
                # Creamos el gráfico con Plotly Express
                fig = px.scatter(
                    df_grafico, 
                    x="Superficie", 
                    y="Precio_m2",
                    hover_data=["Titulo", "Precio"], # Al pasar el mouse se ve el título y el precio total
                    labels={"Superficie": "Superficie (m²)", "Precio_m2": "Valor (U$S / m²)"},
                    color_discrete_sequence=["#1E3A8A"] # Azul corporativo para los puntos
                )
                
                # Agregamos las líneas de tendencia (Mediana y Promedio)
                fig.add_hline(y=mediana_estimada, line_dash="solid", line_color="#10B981", annotation_text=f"Mediana: U$S {mediana_estimada}", annotation_position="top right")
                fig.add_hline(y=promedio_estimado, line_dash="dash", line_color="#EF4444", annotation_text=f"Promedio: U$S {promedio_estimado}", annotation_position="bottom right")
                
                # Ajustes de diseño del gráfico para que coincida con la app
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(showgrid=True, gridcolor='#E2E8F0'),
                    yaxis=dict(showgrid=True, gridcolor='#E2E8F0'),
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                
                # Mostramos el gráfico ocupando todo el ancho
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # --- TABLA DE DATOS ---
                st.markdown("### 📑 Base de Datos de Comparables")
                df_completo = pd.DataFrame(resultados)
                st.dataframe(
                    df_completo, 
                    use_container_width=True,
                    hide_index=True, 
                    column_config={
                        "Precio": st.column_config.NumberColumn("Precio", format="%d"),
                        "Precio_m2": st.column_config.NumberColumn("Valor m²", format="%d"),
                        "Superficie": st.column_config.NumberColumn("Sup. (m²)", format="%d"),
                        "Link": st.column_config.LinkColumn("Ver Publicación", display_text="Abrir enlace ↗")
                    }
                )
            else:
                st.warning("Datos insuficientes en moneda extranjera (USD) para emitir un reporte.")
