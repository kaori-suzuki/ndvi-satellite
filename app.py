import streamlit as st
import numpy as np
from pystac_client import Client
import odc.stac
import folium
from streamlit_folium import st_folium
import matplotlib.cm as cm
import matplotlib.colors as colors
import planetary_computer

st.set_page_config(layout="wide")
st.title("🛰️ NDVI Mapper - Dati Satellitari in Tempo Reale")
st.write("Questa applicazione acquisisce automaticamente gli ultimi dati del satellite Sentinel-2 per le coordinate specificate (latitudine e longitudine), calcola l'Indice di Vegetazione della Differenza Normalizzata (NDVI) e lo visualizza sulla mappa.")

# 1. Input dell'utente (Sidebar)
st.sidebar.header("🔍 Impostazioni")
lat = st.sidebar.number_input("Latitudine (Latitude)", value=44.5222, format="%.6f")  # Valore iniziale: Calderara di Reno, Italia
lon = st.sidebar.number_input("Longitudine (Longitude)", value=11.2727, format="%.6f")
cloud_limit = st.sidebar.slider("Copertura nuvolosa massima (%)", 0, 100, 20)

# Intervallo di date (ultimi 2 mesi circa)
date_range = "2026-08-01/2026-10-06"

if st.sidebar.button("Ottieni Dati Satellitari e Mappa"):
    with st.spinner("Download dei dati più recenti dallo spazio e calcolo dell'NDVI in corso..."):
        
        try:
            # 2. Connessione al catalogo di dati satellitari Microsoft Planetary Computer
            catalog = Client.open(
                "https://microsoft.com",
                modifier=planetary_computer.sign_inplace
            )
            point = {"type": "Point", "coordinates": [lon, lat]}
            
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                intersects=point,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": cloud_limit}},
                sortby=["-properties.datetime"] # Più recente prima
            )
            
            items = list(search.get_items())
            
            if len(items) == 0:
                st.error("Nessun dato con scarsa copertura nuvolosa trovato per il periodo specificato. Modifica le impostazioni delle date o delle nuvole.")
            else:
                latest_item = items[0]
                st.sidebar.success(f"Data di scatto: {latest_item.properties['datetime'][:10]}")
                st.sidebar.info(f"Copertura nuvolosa reale: {latest_item.properties['eo:cloud_cover']:.2f}%")
                
                # 3. Ritaglio dell'area intorno alle coordinate (circa 5 km quadrati)
                bbox = [lon - 0.02, lat - 0.02, lon + 0.02, lat + 0.02]
                data = odc.stac.load([latest_item], bands=["red", "nir"], bbox=bbox, resolution=10)
                
                # 4. Calcolo dell'NDVI (NIR: Vicino Infrarosso, RED: Rosso)
                red = data.red.values.astype(float)
                nir = data.nir.values.astype(float)
                
                # Calcolo NDVI evitando la divisione per zero
                ndvi = (nir - red) / (nir + red + 1e-10)
                
                # Limitazione dei valori tra -1.0 e 1.0
                ndvi = np.clip(ndvi, -1.0, 1.0)
                
                # 5. Mappatura dei colori: Rosso (Nessuna vegetazione) -> Giallo -> Verde (Vegetazione vigorosa)
                norm = colors.Normalize(vmin=0.0, vmax=0.8)
                cmap = cm.get_cmap('RdYlGn') # Mappa dei colori Red-Yellow-Green
                
                # Conversione in dati immagine RGBA
                ndvi_rgba = cmap(norm(ndvi))
                ndvi_rgba = (ndvi_rgba * 255).astype(np.uint8)
                
                # Poiché odc.stac restituisce un array con la dimensione del tempo, prendiamo il primo elemento
                if len(ndvi_rgba.shape) == 4:
                    ndvi_rgba = ndvi_rgba[0]
                
                # 6. Creazione della mappa e sovrapposizione
                m = folium.Map(location=[lat, lon], zoom_start=14, tiles="OpenStreetMap")
                
                # Sovrapposizione dell'immagine NDVI calcolata sulla mappa
                img_bounds = [[lat - 0.02, lon - 0.02], [lat + 0.02, lon + 0.02]]
                folium.raster_layers.ImageOverlay(
                    image=ndvi_rgba,
                    bounds=img_bounds,
                    opacity=0.7,
                    name="Indice di Vegetazione NDVI"
                ).add_to(m)
                
                # Aggiunta di un marker al centro
                folium.Marker([lat, lon], popup="Centro di ricerca").add_to(m)
                folium.LayerControl().add_to(m)
                
                # 7. Visualizzazione sullo schermo di Streamlit
                col1, col2 = st.columns([3, 1])
                with col1:
                    st_folium(m, width=800, height=600)
                
                with col2:
                    st.markdown("### 🎨 Legenda (Come leggere l'NDVI)")
                    st.markdown("🟩 **Verde (0.6〜0.8):** Vegetazione molto vigorosa (colture dense o foreste)")
                    st.markdown("🟨 **Giallo (0.3〜0.5):** Vegetazione moderata (fase di crescita o prati)")
                    st.markdown("🟥 **Rosso (0.0〜0.2):** Quasi nessuna vegetazione (suolo nudo, strade, edifici)")
                    st.markdown("🟦 **(Blu / Rosso scuro):** Superfici d'acqua o ombre")
                    
        except Exception as e:
            st.error(f"Si è verificato un errore durante l'elaborazione dei dati: {e}")
