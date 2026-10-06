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
st.write("Clicca su un punto qualsiasi della mappa per posizionare l'indicatore (pin 📍) e calcolare istantaneamente l'indice NDVI della vegetazione circostante.")

# 1. 保管庫（Session State）の準備（ピンの位置を記憶する）
if "current_lat" not in st.session_state:
    st.session_state.current_lat = 44.5222  # 初期値：ボローニャ
if "current_lon" not in st.session_state:
    st.session_state.current_lon = 11.2727
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 13
if "ndvi_map" not in st.session_state:
    st.session_state.ndvi_map = None
if "legenda_info" not in st.session_state:
    st.session_state.legenda_info = None

# 2. サイドバーの設定
st.sidebar.header("🔍 Impostazioni")
cloud_limit = st.sidebar.slider("Copertura nuvolosa massima (%)", 0, 100, 40)

# 現在のピンの位置を画面に表示
st.sidebar.write("### 📍 Posizione Corrente:")
st.sidebar.info(f"Latitudine: {st.session_state.current_lat:.4f}\n\nLongitudine: {st.session_state.current_lon:.4f}")

# 3. 宇宙データ基地からのデータ取得処理（関数化してスッキリさせました）
def carica_dati_satellite(lat, lon, cloud_max):
    try:
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
            query={"eo:cloud_cover": {"lt": cloud_max}},
            sortby=["-properties.datetime"]
        )
        
        items = list(search.get_items())
        
        if len(items) == 0:
            st.sidebar.error("Nessun dato recente trovato. Prova ad aumentare la nuvolosità massima.")
            return None, None
        
        latest_item = items[0]
        delta = 0.02  # 約5km四方を分析
        bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
        
        data = odc.stac.load([latest_item], bands=["red", "nir"], bbox=bbox, resolution=10)
        
        red = data.red.values.astype(float)
        nir = data.nir.values.astype(float)
        
        if len(red.shape) == 3:
            red = red[0]
            nir = nir[0]
            
        ndvi = (nir - red) / (nir + red + 1e-10)
        ndvi = np.clip(ndvi, -1.0, 1.0)
        
        norm = colors.Normalize(vmin=0.1, vmax=0.5)  # コントラストをパキッと調整済
        try:
            cmap = plt.get_cmap('RdYlGn')
        except Exception:
            cmap = cm.get_cmap('RdYlGn')
            
        ndvi_rgba = cmap(norm(ndvi))
        ndvi_rgba = (ndvi_rgba * 255).astype(np.uint8)
        
        return ndvi_rgba, latest_item
    except Exception as e:
        st.sidebar.error(f"Errore di connessione: {e}")
        return None, None

# 4. 「分析実行」ボタン
if st.sidebar.button("🚀 Calcola NDVI in questa posizione"):
    with st.spinner("Acquisizione dati dal satellite Sentinel-2..."):
        res_rgba, item_info = carica_dati_satellite(st.session_state.current_lat, st.session_state.current_lon, cloud_limit)
        if res_rgba is not None:
            st.session_state.ndvi_map = res_rgba
            st.session_state.legenda_info = {
                "data": item_info.properties['datetime'][:10],
                "cloud": item_info.properties['eo:cloud_cover']
            }

# 5. 画面のメインエリア（地図の表示とクリック検知）
col1, col2 = st.columns([3, 1])

with col1:
    # ベースの地図を作成
    m_render = folium.Map(
        location=[st.session_state.current_lat, st.session_state.current_lon], 
        zoom_start=st.session_state.map_zoom, 
        tiles="OpenStreetMap"
    )
    
    # すでに計算済みのNDVI画像があれば地図に重ねる
    if st.session_state.ndvi_map is not None:
        delta = 0.02
        img_bounds = [
            [st.session_state.current_lat - delta, st.session_state.current_lon - delta], 
            [st.session_state.current_lat + delta, st.session_state.current_lon + delta]
        ]
        folium.raster_layers.ImageOverlay(
            image=st.session_state.ndvi_map,
            bounds=img_bounds,
            opacity=0.6,
            name="NDVI"
        ).add_to(m_render)
    
    # 📍 あなたが自由自在に動かせる「雫の反対のマーク」
    folium.Marker(
        [st.session_state.current_lat, st.session_state.current_lon], 
        popup="Analisi qui",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(m_render)
    
    # 地図を表示し、クリック（タップ）を監視
    map_output = st_folium(m_render, width=850, height=600, key="map_scouting")
    
    # 【💡超重要】地図のどこかが新しくクリックされたら、ピンの位置をそこにワープさせる！
    if map_output and map_output.get("last_clicked"):
        clicked_lat = map_output["last_clicked"]["lat"]
        clicked_lng = map_output["last_clicked"]["lng"]
        
        # わずかでも違う場所がクリックされたらピンの座標を更新
        if abs(clicked_lat - st.session_state.current_lat) > 1e-5 or abs(clicked_lng - st.session_state.current_lon) > 1e-5:
            st.session_state.current_lat = clicked_lat
            st.session_state.current_lon = clicked_lng
            st.session_state.map_zoom = map_output["zoom"]
            st.rerun()  # 画面を再起動してピンの位置を確定させる

with col2:
    st.markdown("### 🎨 Legenda (NDVI)")
    st.markdown("🟩 **Verde (0.5+):**\n\nVegetazione molto vigorosa")
    st.markdown("🟨 **Giallo (0.3〜0.4):**\n\nVegetazione moderata")
    st.markdown("🟥 **Rosso (0.1〜0.2):**\n\nSuolo nudo / Edifici")
    
    if st.session_state.legenda_info is not None:
        st.markdown("---")
        st.markdown(f"📅 **Data:** {st.session_state.legenda_info['data']}")
        st.markdown(f"☁️ **Nuvole:** {st.session_state.legenda_info['cloud']:.1f}%")
