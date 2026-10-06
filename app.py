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

st.set_page_config(layout="wide")
st.title("🛰️ NDVI Mapper - Dati Satellitari in Tempo Reale")
st.write("Questa applicazione acquisisce automaticamente gli ultimi dati del satellite Sentinel-2 per le coordinate specificate, calcola l'Indice di Vegetazione della Differenza Normalizzata (NDVI) e lo visualizza sulla mappa.")

# 1. Input dell'utente (Sidebar)
st.sidebar.header("🔍 Impostazioni")

# あなたが提示してくれた選択肢の作成
st.sidebar.write("### Scegli l'estensione geografica per l'analisi del suolo:")
area_scelta = st.sidebar.radio(
    label="Seleziona un'area:",
    options=[
        "📍 Provincia di Bologna (Area di Ricerca e Ground Truth)",
        "🌾 Emilia-Romagna (Carbon Farming Test)",
        "🇮🇹 Italia (Copertura Nazionale - Intero Paese)"
    ],
    label_visibility="collapsed" # ラジオボタン自体のタイトルは隠してすっきりさせる
)

# 選ばれたエリアに応じて、中心点（緯度・経度）と地図の大きさを自動切り替え
if area_scelta == "📍 Provincia di Bologna (Area di Ricerca e Ground Truth)":
    lat = 44.5222
    lon = 11.2727
    zoom_val = 13  # 狭い範囲（町レベル）
    delta = 0.02   # 約5km四方
elif area_scelta == "🌾 Emilia-Romagna (Carbon Farming Test)":
    lat = 44.4949
    lon = 11.3426
    zoom_val = 9   # 中くらいの範囲（州レベル）
    delta = 0.15   # 約35km四方
else:
    lat = 42.5042
    lon = 12.5222
    zoom_val = 6   # 広い範囲（イタリア全土）
    delta = 0.5    # 広範囲

cloud_limit = st.sidebar.slider("Copertura nuvolosa massima (%)", 0, 100, 40)

# 自動で直近3ヶ月のデータを検索
oggi = datetime.now()
tre_mesi_fa = oggi - timedelta(days=90)
date_range = f"{tre_mesi_fa.strftime('%Y-%m-%d')}/{oggi.strftime('%Y-%m-%d')}"

if st.sidebar.button("Ottieni Dati Satellitari e Mappa"):
    with st.spinner("Download dei dati più recenti dallo spazio e calcolo dell'NDVI in corso..."):
        
        try:
            # 2. Connessione al catalogo Microsoft
            catalog = Client.open(
                "https://planetarycomputer.microsoft.com/api/stac/v1",
                modifier=planetary_computer.sign_inplace
            )
            point = {"type": "Point", "coordinates": [lon, lat]}
            
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
                latest_item = items
                st.sidebar.success(f"Data di scatto: {latest_item.properties['datetime'][:10]}")
                st.sidebar.info(f"Copertura nuvolosa reale: {latest_item.properties['eo:cloud_cover']:.2f}%")
                
                # 3. 選択された範囲に応じて切り出しサイズを変更
                bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
                
                # 広範囲の場合は解像度を少し粗く(30m)して速度を爆速にする
                res_val = 30 if delta > 0.2 else 10
                data = odc.stac.load([latest_item], bands=["red", "nir"], bbox=bbox, resolution=res_val)
                
                # 4. Calcolo dell'NDVI
                red = data.red.values.astype(float)
                nir = data.nir.values.astype(float)
                
                ndvi = (nir - red) / (nir + red + 1e-10)
                ndvi = np.clip(ndvi, -1.0, 1.0)
                
                # 5. Mappatura dei colori (修正済み最新版)
                norm = colors.Normalize(vmin=0.0, vmax=0.8)
                cmap = st.pyplot.matplotlib.colormaps.get_cmap('RdYlGn') if hasattr(st, 'pyplot') else cm.get_cmap('RdYlGn')
                
                ndvi_rgba = cmap(norm(ndvi))
                ndvi_rgba = (ndvi_rgba * 255).astype(np.uint8)
                
                # 6. Creazione della mappa Folium
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
                
                # 7. Visualizzazione in Streamlit
                col1, col2 = st.columns()
                with col1:
                    st_folium(m, width=800, height=600)
                with col2:
                    st.markdown("### 🎨 Legenda (Come leggere l'NDVI)")
                    st.markdown("🟩 **Verde (0.6〜0.8):** Vegetazione molto vigorosa")
                    st.markdown("🟨 **Giallo (0.3〜0.5):** Vegetazione moderata")
                    st.markdown("🟥 **Rosso (0.0〜0.2):** Quasi nessuna vegetazione")
                    st.markdown("🟦 **(Blu / Rosso scuro):** Superfici d'acqua o ombre")
                    
        except Exception as e:
            st.error(f"Si è verificato un errore: {e}")
