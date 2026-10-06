import streamlit as st
import numpy as np
from pystac_client import Client
import odc.stac
import folium
from streamlit_folium import st_folium
import matplotlib.cm as cm
import matplotlib.colors as colors

st.set_page_config(layout="wide")
st.title("🛰️ リアルタイム衛星データ NDVIマッパー")
st.write("指定した座標（緯度・経度）の最新のSentinel-2衛星データを自動取得し、植生指標(NDVI)を計算してマップに可視化します。")

# 1. ユーザーからの入力エリア（サイドバー）
st.sidebar.header("🔍 条件設定")
lat = st.sidebar.number_input("緯度 (Latitude)", value=35.6895, format="%.6f")  # 初期値：東京
lon = st.sidebar.number_input("経度 (Longitude)", value=139.6917, format="%.6f")
cloud_limit = st.sidebar.slider("許容する雲の量 (%)", 0, 100, 20)

# 日付範囲（直近2ヶ月程度を設定）
date_range = "2026-08-01/2026-10-06"

if st.sidebar.button("衛星データを取得してマッピング"):
    with st.spinner("宇宙から最新データをダウンロードし、NDVIを計算中..."):
        
        try:
            # 2. 無料の衛星データカタログへ接続
            catalog = Client.open("https://element84.com")
            point = {"type": "Point", "coordinates": [lon, lat]}
            
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                intersects=point,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": cloud_limit}},
                sortby=["-properties.datetime"] # 最新順
            )
            
            items = list(search.get_items())
            
            if len(items) == 0:
                st.error("指定された期間内に雲の少ないデータが見つかりませんでした。日付や雲の量の設定を変更してください。")
            else:
                latest_item = items[0]
                st.sidebar.success(f"撮影日: {latest_item.properties['datetime'][:10]}")
                st.sidebar.info(f"実際の雲の量: {latest_item.properties['eo:cloud_cover']:.2f}%")
                
                # 3. 座標の周辺（約5km四方）を切り抜いてデータを読み込む
                # 緯度経度の微小な変化で範囲を決定
                bbox = [lon - 0.02, lat - 0.02, lon + 0.02, lat + 0.02]
                data = odc.stac.load([latest_item], bands=["red", "nir"], bbox=bbox, resolution=10)
                
                # 4. NDVIの計算 (近赤外: nir, 赤: red)
                red = data.red.values[0].astype(float)
                nir = data.nir.values[0].astype(float)
                
                # ゼロ除算を回避してNDVI計算（-1.0 〜 1.0 に収まる）
                ndvi = (nir - red) / (nir + red + 1e-10)
                
                # 有効な値のマスク処理（水域やエラー値の除外）
                ndvi = np.clip(ndvi, -1.0, 1.0)
                
                # 5. 緑・黄・赤のカラーマッピング処理
                # 赤(植物なし) -> 黄 -> 緑(植物元気) のグラデーションを作る
                # NDVIの一般的な範囲 0.0(赤)〜0.8(緑) にマッピング
                norm = colors.Normalize(vmin=0.0, vmax=0.8)
                cmap = cm.get_cmap('rdylgn') # Red-Yellow-Greenのカラーマップ
                
                # RGBAの画像データに変換
                ndvi_rgba = cmap(norm(ndvi))
                ndvi_rgba = (ndvi_rgba * 255).astype(np.uint8)
                
                # 6. 地図の作成と重ね合わせ
                m = folium.Map(location=[lat, lon], zoom_start=14, tiles="OpenStreetMap")
                
                # 計算したNDVI画像を地図上にオーバーレイ
                # 座標の上下左右の端を計算
                img_bounds = [[lat - 0.02, lon - 0.02], [lat + 0.02, lon + 0.02]]
                folium.raster_layers.ImageOverlay(
                    image=ndvi_rgba,
                    bounds=img_bounds,
                    opacity=0.7,
                    name="NDVI植生指標"
                ).add_to(m)
                
                # 中心点にピンを立てる
                folium.Marker([lat, lon], popup="検索中心点").add_to(m)
                folium.LayerControl().add_to(m)
                
                # 7. Streamlitの画面に表示
                col1, col2 = st.columns([3, 1])
                with col1:
                    st_folium(m, width=800, height=600)
                
                with col2:
                    st.markdown("### 🎨 凡例 (NDVIの見方)")
                    st.markdown("🟩 **緑色 (0.6〜0.8):** 植物がとても元気（密生した作物や森林）")
                    st.markdown("🟨 **黄色 (0.3〜0.5):** 植物がそこそこある（成長途中、または草地）")
                    st.markdown("🟥 **赤色 (0.0〜0.2):** 植物がほぼ無い（土壌、道路、建物）")
                    st.markdown("🟦 **（青/濃赤）:** 水面や影など")
                    
        except Exception as e:
            st.error(f"データの処理中にエラーが発生しました: {e}")
