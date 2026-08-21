import streamlit as st
import pandas as pd
import requests
import io
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="OOH Media in SEOUL", layout="wide")
st.title("🏙️ OOH Media in SEOUL")

KAKAO_API_KEY = "9f98264d7ef44f83084608ac07349c0b"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1mosGrKlMC4wggbf6VPjt3aQLm-R3WIPzVYbGoXVjeFY/export?format=csv&gid=1134856496"

@st.cache_data(ttl=60)
def load_data(url):
    res = requests.get(url)
    res.raise_for_status()
    df = pd.read_csv(io.StringIO(res.text))
    df.columns = df.columns.str.strip()
    return df

try:
    df = load_data(SHEET_URL)
except Exception:
    st.error("데이터 로드 실패")
    st.stop()

@st.cache_data
def get_lat_lon(address, api_key):
    api_url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    try:
        res = requests.get(api_url, headers=headers, params={"query": address}, timeout=5)
        docs = res.json().get('documents')
        if docs: return float(docs[0]['y']), float(docs[0]['x'])
    except:
        pass
    return None, None

if 'LAT' not in df.columns or 'LON' not in df.columns:
    with st.spinner("좌표 변환 중..."):
        df['LAT'], df['LON'] = zip(*df['LOCATION'].apply(lambda x: get_lat_lon(x, KAKAO_API_KEY)))

map_data = df.dropna(subset=['LAT', 'LON'])

def get_github_image_url(raw_id):
    try:
        id_str = str(raw_id).strip()
        if id_str.endswith('.0'): id_str = id_str[:-2]
        id_str_z3 = str(int(float(id_str))).zfill(3)
        return f"https://github.com/JLee900430/OOH_Map_Seoul/blob/main/{id_str_z3}_A.jpg?raw=true"
    except Exception:
        return ""

@st.cache_resource
def create_map(data_hash):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    legend_html = """
    <div style="position: fixed; top: 15px; left: 60px; width: 220px; height: 135px; background-color: white; z-index:9999; font-size:12px; border:2px solid #ccc; border-radius: 8px; padding: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
      <b style="font-size: 14px; color: #111;">🏙️ OOH Media in SEOUL</b><hr style="margin: 5px 0; border:0; border-top:1px solid #eee;">
      <div><span style="background:#3498db; width:12px; height:12px; display:inline-block; border-radius:50%; margin-right:6px; vertical-align: middle;"></span> LED</div>
      <div><span style="background:#2ecc71; width:12px; height:12px; display:inline-block; border-radius:50%; margin-right:6px; vertical-align: middle;"></span> STATIC</div>
      <div><span style="background:#9b59b6; width:12px; height:12px; display:inline-block; border-radius:50%; margin-right:6px; vertical-align: middle;"></span> LED + STATIC</div>
      <div><span style="background:#e74c3c; width:12px; height:12px; display:inline-block; border-radius:3px; margin-right:6px; vertical-align: middle;"></span> 불법 매체</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    
    for (lat, lon), group in map_data.groupby(['LAT', 'LON']):
        types = group['TYPE'].astype(str).tolist()
        type_str = " ".join(types).upper()
        bg_color = '#9b59b6' if 'LED' in type_str and ('STATIC' in type_str or '+' in type_str) else ('#3498db' if 'LED' in type_str else '#2ecc71')
        is_illegal = any("불법" in str(val).replace(" ", "") for val in group['LEGAL'].values)
        
        # 💡 호버링용 프리뷰 (Tooltip)
        tooltip_items = ""
        # 💡 클릭용 상세 팝업 (Popup) - Streamlit 우측 패널을 완벽 대체!
        popup_items = ""
        
        for _, row in group.iterrows():
            m_name, m_price, m_period = row.get('NAME', ''), row.get('PRICE', ''), row.get('PERIOD', '')
            img_url = get_github_image_url(row.get('ID', ''))
            
            # 호버링 디자인
            img_tag_small = f'<br><img src="{img_url}" style="width:100%; height:80px; object-fit:cover; border-radius:4px; margin-top:4px;" onerror="this.style.display=\'none\'" />' if img_url else ''
            tooltip_items += f"""
            <div style="background: #fdfdfd; border: 1px solid #e0e0e0; padding: 6px; border-radius: 6px;">
                <b style="font-size: 11px;">{m_name}</b><br><span style="font-size: 10px; color: #e74c3c;">💰 {m_price}원</span>{img_tag_small}
            </div>
            """
            
            # 클릭 상세 디자인
            img_tag_large = f'<img src="{img_url}" style="width:100%; max-height:200px; object-fit:contain; border-radius:8px; margin-top:10px;" onerror="this.style.display=\'none\'" />' if img_url else ''
            popup_items += f"""
            <div style="margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 10px;">
                <h4 style="margin:0 0 5px 0; color:#333;">🏷️ {m_name}</h4>
                <p style="margin:2px 0; font-size:12px;"><b>유형:</b> {row.get('TYPE', '')}</p>
                <p style="margin:2px 0; font-size:12px;"><b>단가:</b> {m_price}원 ({m_period})</p>
                <p style="margin:2px 0; font-size:12px;"><b>주소:</b> {row.get('LOCATION', '')}</p>
                <p style="margin:2px 0; font-size:12px; color:#666;">{row.get('Details', '')}</p>
                {img_tag_large}
            </div>
            """

        grid_cols = "repeat(2, 1fr)" if len(group) > 1 else "1fr"
        tooltip_html = f"""<div style="font-family: sans-serif; padding: 5px; width: {400 if len(group) > 1 else 200}px;"><div style="display: grid; grid-template-columns: {grid_cols}; gap: 5px;">{tooltip_items}</div></div>"""
        
        popup_html = f"""<div style="font-family: sans-serif; width: 350px; max-height: 400px; overflow-y: auto; padding: 10px;">{popup_items}</div>"""

        badge_html = '<div style="position: absolute; top:-10px; right:-16px; background-color:#e74c3c; color:white; font-size:9px; font-weight:bold; padding:1px 3px; border-radius:3px; border:1px solid white; z-index:10;">불법</div>' if is_illegal else ''
        
        html_content = f"""
        <div style="position: relative; display: inline-block;">
            <div style="background-color: {bg_color}; width: 26px; height: 26px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 11px;">{len(group) if len(group) > 1 else '📍'}</div>
            {badge_html}
        </div>
        """
        
        # 단일 마커에 Tooltip(호버)과 Popup(클릭) 동시 적용
        folium.Marker(
            [lat, lon], 
            icon=folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16)),
            tooltip=folium.Tooltip(tooltip_html, parse_html=True),
            popup=folium.Popup(popup_html, max_width=400)
        ).add_to(m)
        
    return m

map_obj = create_map(len(map_data))

# 💡 더 이상 파이썬 클릭 이벤트를 감지할 필요가 없으므로 화면이 절대 새로고침되지 않습니다.
st_folium(map_obj, width="100%", height=850, returned_objects=[])
