import streamlit as st
import pandas as pd
import requests
import io
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="OOH Media in SEOUL", layout="wide")

# Session State 초기화
if 'mix_mode' not in st.session_state:
    st.session_state.mix_mode = False
if 'mix_list' not in st.session_state:
    st.session_state.mix_list = []
if 'last_added_coords' not in st.session_state:
    st.session_state.last_added_coords = None

# 상단 헤더 & 모드 전환 버튼
col_title, col_mix_btn = st.columns([8, 2])
with col_title:
    st.title("🏙️ OOH Media in SEOUL" + (" (🛒 믹스 만들기 모드)" if st.session_state.mix_mode else ""))

with col_mix_btn:
    st.write("") # 수직 정렬용 여백
    if st.session_state.mix_mode:
        if st.button("⬅️ 일반 지도로 돌아가기", type="primary", use_container_width=True):
            st.session_state.mix_mode = False
            st.rerun()
    else:
        if st.button("🛒 믹스 만들기 켜기", use_container_width=True):
            st.session_state.mix_mode = True
            st.rerun()

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

def get_github_image_urls(raw_id):
    try:
        id_str = str(raw_id).strip()
        if id_str.endswith('.0'): id_str = id_str[:-2]
        id_str_z3 = str(int(float(id_str))).zfill(3)
        base = "https://github.com/JLee900430/OOH_Map_Seoul/blob/main"
        return [f"{base}/{id_str_z3}_A.jpg?raw=true", f"{base}/{id_str_z3}_B.jpg?raw=true"]
    except Exception:
        return ["", ""]

def format_text_with_br(val):
    if pd.isna(val): return ""
    return str(val).replace('\n', '<br>')

@st.cache_resource
def create_map(data_hash, is_mix_mode):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 툴팁 및 팝업 화면 최적화 CSS
    custom_css = """
    <style>
    .leaflet-tooltip {
        max-width: 320px !important;
        white-space: normal !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2) !important;
    }
    .leaflet-popup-content-wrapper {
        border-radius: 12px !important;
        box-shadow: 0 8px 25px rgba(0,0,0,0.25) !important;
    }
    </style>
    """
    m.get_root().html.add_child(folium.Element(custom_css))
    
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
        
        tooltip_items = ""
        popup_items = ""
        
        for _, row in group.iterrows():
            m_name = format_text_with_br(row.get('NAME', ''))
            m_price = format_text_with_br(row.get('PRICE', ''))
            m_period = format_text_with_br(row.get('PERIOD', ''))
            m_type = format_text_with_br(row.get('TYPE', ''))
            m_location = format_text_with_br(row.get('LOCATION', ''))
            m_details = format_text_with_br(row.get('Details', ''))
            
            img_urls = get_github_image_urls(row.get('ID', ''))
            
            # 호버링 툴팁용 작은 이미지
            img_tag_small = f'<br><img src="{img_urls[0]}" style="width:100%; height:80px; object-fit:cover; border-radius:4px; margin-top:4px;" onerror="this.style.display=\'none\'" />' if img_urls[0] else ''
            tooltip_items += f"""
            <div style="background: #fdfdfd; border: 1px solid #e0e0e0; padding: 6px; border-radius: 6px;">
                <b style="font-size: 11px;">{m_name}</b><br><span style="font-size: 10px; color: #e74c3c;">💰 {m_price}원</span>{img_tag_small}
            </div>
            """
            
            if not is_mix_mode:
                # 💡 팝업창 내부 이미지 크기를 대폭 확대 (높이 350px, 선명한 화질 유지)
                img_tag_large_1 = f'<img src="{img_urls[0]}" style="width:48%; height:350px; object-fit:cover; border-radius:8px; box-shadow:0 4px 10px rgba(0,0,0,0.15);" onerror="this.style.display=\'none\'" />' if img_urls[0] else ''
                img_tag_large_2 = f'<img src="{img_urls[1]}" style="width:48%; height:350px; object-fit:cover; border-radius:8px; box-shadow:0 4px 10px rgba(0,0,0,0.15);" onerror="this.style.display=\'none\'" />' if img_urls[1] else ''
                
                popup_items += f"""
                <div style="margin-bottom: 25px; border-bottom: 2px solid #eee; padding-bottom: 20px;">
                    <h2 style="margin:0 0 12px 0; color:#111; font-size:20px;">🏷️ {m_name}</h2>
                    <div style="display:flex; justify-content:space-between; font-size:15px; background:#f8f9fa; padding:14px; border-radius:8px; margin-bottom:14px;">
                        <div><b>유형:</b> {m_type}<br><b>주소:</b> {m_location}</div>
                        <div style="text-align:right; color:#e74c3c;"><b>단가:</b> {m_price}원<br>({m_period})</div>
                    </div>
                    <p style="margin:4px 0 15px 0; font-size:14px; color:#444; line-height:1.6;">{m_details}</p>
                    <div style="display:flex; justify-content:space-between; gap:10px;">
                        {img_tag_large_1}
                        {img_tag_large_2}
                    </div>
                </div>
                """

        grid_cols = "repeat(2, 1fr)" if len(group) > 1 else "1fr"
        tooltip_html = f"""<div style="font-family: sans-serif; padding: 2px; max-width: 320px;"><div style="display: grid; grid-template-columns: {grid_cols}; gap: 5px;">{tooltip_items}</div></div>"""
        
        badge_html = '<div style="position: absolute; top:-10px; right:-16px; background-color:#e74c3c; color:white; font-size:9px; font-weight:bold; padding:1px 3px; border-radius:3px; border:1px solid white; z-index:10;">불법</div>' if is_illegal else ''
        
        html_content = f"""
        <div style="position: relative; display: inline-block;">
            <div style="background-color: {bg_color}; width: 26px; height: 26px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 11px;">{len(group) if len(group) > 1 else '📍'}</div>
            {badge_html}
        </div>
        """
        
        if is_mix_mode:
            folium.Marker(
                [lat, lon], 
                icon=folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16)),
                tooltip=folium.Tooltip(tooltip_html, parse_html=True, direction='auto')
            ).add_to(m)
        else:
            # 💡 팝업창 전체 크기 확대 (가로 850px, 최대 높이 700px, 스크롤바 제공) 및 화면 밖 잘림 방지 설정 적용
            popup_html = f"""<div style="font-family: sans-serif; width: 850px; max-height: 700px; overflow-y: auto; padding: 20px;">{popup_items}</div>"""
            folium.Marker(
                [lat, lon], 
                icon=folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16)),
                tooltip=folium.Tooltip(tooltip_html, parse_html=True, direction='auto'),
                popup=folium.Popup(popup_html, max_width=900, keep_in_view=True)
            ).add_to(m)
        
    return m

map_obj = create_map(len(map_data), st.session_state.mix_mode)

if st.session_state.mix_mode:
    col_map, col_mix = st.columns([7, 3])
    returned_objects = ['last_object_clicked']
else:
    col_map = st.container()
    col_mix = None
    returned_objects = []

with col_map:
    if st.session_state.mix_mode:
        st.info("👆 지도에서 마커를 클릭하여 우측 믹스 보드에 매체를 추가하세요.")
    map_output = st_folium(map_obj, width="100%", height=850, returned_objects=returned_objects, key="main_stable_map")

if st.session_state.mix_mode and map_output and map_output.get('last_object_clicked'):
    c_lat, c_lon = map_output['last_object_clicked']['lat'], map_output['last_object_clicked']['lng']
    current_click = f"{c_lat}_{c_lon}"
    
    if current_click != st.session_state.last_added_coords:
        unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
        unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
        closest_idx = unique_coords['dist_sq'].idxmin()
        
        if unique_coords.loc[closest_idx, 'dist_sq'] < 0.0005:
            lat, lon = unique_coords.loc[closest_idx, 'LAT'], unique_coords.loc[closest_idx, 'LON']
            matched = map_data[(map_data['LAT'] == lat) & (map_data['LON'] == lon)]
            
            added_count = 0
            for _, row in matched.iterrows():
                if row['NAME'] not in [item['NAME'] for item in st.session_state.mix_list]:
                    st.session_state.mix_list.append(row.to_dict())
                    added_count += 1
            
            st.session_state.last_added_coords = current_click
            if added_count > 0:
                st.rerun()

if st.session_state.mix_mode and col_mix:
    with col_mix:
        st.subheader("🛒 미디어 믹스 보드")
        st.markdown("---")
        
        if not st.session_state.mix_list:
            st.warning("아직 추가된 매체가 없습니다. 마커를 클릭하세요.")
        else:
            total_price = 0
            for idx, item in enumerate(st.session_state.mix_list):
                col_info, col_del = st.columns([8, 2])
                with col_info:
                    st.markdown(f"**{item['NAME']}**")
                    st.caption(f"{item['TYPE']} | {item['PRICE']}원")
                with col_del:
                    if st.button("❌", key=f"del_{idx}"):
                        st.session_state.mix_list.pop(idx)
                        st.session_state.last_added_coords = None
                        st.rerun()
                st.markdown("---")
                
                try:
                    price_str = str(item['PRICE']).replace(',', '').replace('원', '').strip()
                    total_price += int(price_str)
                except ValueError:
                    pass
            
            st.success(f"**총 예상 단가 합계:**\n### {total_price:,} 원")
