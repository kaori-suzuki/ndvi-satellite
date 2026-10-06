import streamlit as st
import numpy as np
from pystac_client import Client
import odc.stac
import folium
from streamlit_folium import st_folium
import matplotlib.cm as cm
import matplotlib.colors as colors
import planetary_computer
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")
st.title("🛰️ NDVI Mapper - Dati Satellitari in Tempo Reale")
st.write("Questa applicazione acquisisce automaticamente gli ultimi dati del satellite Sentinel-2 per le coordinate specificate, calcola l'Indice di Vegetazione della Differenza Normalizzata (NDVI) e lo visualizza sulla mappa.")

# 1. Input dell'utente (Sidebar)
st.sidebar.header("🔍 Impostazioni")

st.sidebar.write("### Scegli l'estensione geografica per l'analisi del suolo:")
area_scelta = st.sidebar.radio(
    label="Seleziona un'area:",
    options=[
        "📍 Provincia di Bologna ",
        "🌾 Emilia-Romagna ",
        "🇮🇹 Italia (Copertura Nazionale)"
    ],
    label_visibility="collapsed"
)

# エリアに応じた設定（スペースの数を完全に統一）
if area_scelta == "📍 Provincia di Bologna ":
    lat, lon, zoom_val, delta = 44.5222, 11.2727, 13, 0.02
elif area_scelta == "🌾 Emilia-Romagna ":
    lat, lon, zoom_val, delta = 44.4949, 11.3426, 9, 0.15
else:
    lat, lon, zoom_val, delta = 42.5042, 12.5222, 6, 0.4

cloud_limit = st.sidebar.slider("Copertura nuvolosa massima (%)", 0, 100, 40)

# 画面が消えるのを防ぐ保管庫の準備
if "ndvi_map" not in st.session_state:
    st.session_state.ndvi_map = None
if "legenda_info" not in st.session_state:
    st.session_state.legenda_info = None

if st.sidebar.button("Ottieni Dati Satellitari e Mappa"):
    with st.spinner("Download dei dati più recenti dallo spazio e calcolo dell'NDVI in corso..."):
        try:
            # 2. Connessione al catalogo Microsoft
            catalog = Client.open(
                "https://planetarycomputer.microsoft.com/api/stac/v1",
                modifier=planetary_computer.sign_inplace
            )
            point = {"type": "Point", "coordinates": [lon, lat]}
            
            oggi = datetime.now()
            tre_mesi_fa = oggi - timedelta(days=90)
            date_range = f"{tre_mesi_fa.strftime('%Y-%m-%d')}/{oggi.strftime('%Y-%m-%d')}"
            
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                intersects=point,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": cloud_limit}},
                sortby=["-properties.datetime"]
            )
            
            items = list(search.get_items())
            
            if len(items) == 0:
                st.error("Nessun dato recente trovato. Prova ad aumentare la 'Copertura nuvolosa massima'.")
            else:
                # 【★ここを完全に修正！】リストの「最初の1枚」を確実に指定する
                latest_item = items[0]
                
                # 3. データの読み込み（[latest_item] というリスト形式で渡す）
                bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
                res_val = 30 if delta > 0.2 else 10
                data = odc.stac.load([latest_item], bands=["red", "nir"], bbox=bbox, resolution=res_val)
                
                # 4. NDVIの計算
                red = data.red.values.astype(float)
                nir = data.nir.values.astype(float)
                
                # 3次元配列から時間軸を潰す処理
                if len(red.shape) == 3:
                    red = red[0]
                    nir = nir[0]
                
                ndvi = (nir - red) / (nir + red + 1e-10)
                ndvi = np.clip(ndvi, -1.0, 1.0)
                
                # 5. カラーマッピング（新旧対応の絶対安全コード）
                norm = colors.Normalize(vmin=0.0, vmax=0.8)
                try:
                    cmap = plt.get_cmap('RdYlGn')
                except Exception:
                    cmap = cm.get_cmap('RdYlGn')
                
                ndvi_rgba = cmap(norm(ndvi))
                ndvi_rgba = (ndvi_rgba * 255).astype(np.uint8)
                
                # 6. 地図の作成
                m = folium.Map(location=[lat, lon], zoom_start=zoom_val, tiles="OpenStreetMap")
                img_bounds = [[lat - delta, lon - delta], [lat + delta, lon + delta]]
                
                folium.raster_layers.ImageOverlay(
                    image=ndvi_rgba,
                    bounds=img_bounds,
                    opacity=0.7,
                    name="Indice di Vegetazione NDVI"
                ).add_to(m)
                
                folium.Marker([lat, lon], popup="Centro analisi").add_to(m)
                folium.LayerControl().add_to(m)
                
                               # 保管庫に保存する（地図ではなく画像データを保存する形に変更）
                st.session_state.ndvi_map = ndvi_rgba
                st.session_state.legenda_info = {
                    "data": latest_item.properties['datetime'][:10],
                    "cloud": latest_item.properties['eo:cloud_cover']
                }
 
        except Exception as e:
            st.error(f"Si è verificato un errore: {e}")

# 保管庫にデータがあれば表示を維持する
if st.session_state.ndvi_map is not None:
    st.sidebar.success(f"Data di scatto: {st.session_state.legenda_info['data']}")
    st.sidebar.info(f"Copertura nuvolosa reale: {st.session_state.legenda_info['cloud']:.2f}%")
    
    col1, col2 = st.columns(2)
    with col1:
        # 保管庫の画像データを使って、安全に地図を再構築して表示
        m_render = folium.Map(location=[lat, lon], zoom_start=zoom_val, tiles="OpenStreetMap")
        img_bounds = [[lat - delta, lon - delta], [lat + delta, lon + delta]]
        
        folium.raster_layers.ImageOverlay(
            image=st.session_state.ndvi_map,
            bounds=img_bounds,
            opacity=0.7,
            name="Indice di Vegetazione NDVI"
        ).add_to(m_render)
        
        folium.Marker([lat, lon], popup="Centro analisi").add_to(m_render)
        folium.LayerControl().add_to(m_render)
        
        # 安全な地図を表示
        st_folium(m_render, width=800, height=600, key="fixed_ndvi_map")

   with col2:
        st.markdown("### 🎨 Legenda (Come leggere l'NDVI)")
        st.markdown("🟩 **Verde (0.6〜0.8):** Vegetazione molto vigorosa")
        st.markdown("🟨 **Giallo (0.3〜0.5):** Vegetazione moderata")
        st.markdown("🟥 **Rosso (0.0〜0.2):** Quasi nessuna vegetazione")
        st.markdown("🟦 **(Blu / Rosso scuro):** Superfici d'acqua o ombre")
