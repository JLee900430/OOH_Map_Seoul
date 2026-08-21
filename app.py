import streamlit as st
import pandas as pd
import requests
import io
import os
import numpy as np
from PIL import Image
from streamlit_folium import st_folium
import folium

# 1. 페이지 설정 및 초기화
st.set_page_config(page_title="OOH Media in SEOUL", layout="wide")
st.title("🏙️ OOH Media in SEOUL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 사이드바 설정
st.sidebar.header("⚙️ 환경 설정")
KAKAO_API_KEY = st.sidebar.text_input("카카오 API 키", value="9f98264d7ef44f83084608ac07349c0b")
SHEET_URL = st.sidebar.text_input("구글 시트 CSV 링크", value="https://docs.google.com/spreadsheets/d/1mosGrKlMC4wggbf6VPjt3aQLm-R3WIPzVYbGoXVjeFY/export?format=csv&gid=1134856496")
user_img_dir = st.sidebar.text_input("이미지 폴더 경로 (비워두면 app.py와 같은 경로)", value="")

IMAGE_DIR = user_img_dir if (user_img_dir and os.path.isabs(user_img_dir)) else (os.path.join(BASE_DIR, user_img_dir) if user_img_dir and user_img_dir != "." else BASE_DIR)

# 3. 구글 시트 데이터 로드
@st.cache_data(ttl=60)
def load_data(url):
    res = requests.get(url)
    res.raise_for_status()
    df = pd.read_csv(io.StringIO(res.text))
    df.columns = df.columns.str.strip()
    return df

try:
    df = load_data(SHEET_URL)
except Exception as e:
    st.error(f"구글 시트 데이터를 불러오는 데 실패했습니다: {e}")
    st.stop()

@st.cache_data
def get_lat_lon(address, api_key):
    api_url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    try:
        res = requests.get(api_url, headers=headers, params={"query": address}, timeout=5)
        docs = res.json().get('documents')
        if docs:
            return float(docs[0]['y']), float(docs[0]['x'])
    except Exception:
        pass
    return None, None

if 'LAT' not in df.columns or 'LON' not in df.columns:
    with st.spinner("주소를 좌표로 변환 중..."):
        df['LAT'], df['LON'] = zip(*df['LOCATION'].apply(lambda x: get_lat_lon(x, KAKAO_API_KEY)))

map_data = df.dropna(subset=['LAT', 'LON'])
if len(map_data) == 0:
    st.warning("⚠️ 지도에 표시할 마커가 없습니다.")

# 4. 메모리 폭발 주범이었던 이미지 사전 로딩 제거! (경량화 핵심)
if 'clicked_lat' not in st.session_state:
    st.session_state.clicked_lat = None
if 'clicked_lon' not in st.session_state:
    st.session_state.clicked_lon = None

# 5. 초경량 지도 생성 함수 (메모리 에러 완벽 차단)
@st.cache_resource
def create_lightweight_map(data_hash):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 범례 유지
    legend_html = """
    <div style="position: fixed; top: 15px; left: 60px; width: 220px; height: 135px; background-color: white; z-index:9999; font-size:12px; border:2px solid #ccc; border-radius: 8px; padding: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-family: sans-serif; line-height: 1.5;">
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
        
        # 💡 호버링 이미지를 뺀 '텍스트 전용 툴팁'으로 메모리 최적화
        tooltip_items_html = ""
        for _, row in group.iterrows():
            tooltip_items_html += f"""
            <div style="border-bottom: 1px solid #eee; padding: 4px 0;">
                <b style="font-size: 13px; color: #111;">{row.get('NAME', '')}</b><br>
                <span style="font-size: 11px; color: #e74c3c; font-weight: bold;">💰 {row.get('PRICE', '')} 원 ({row.get('PERIOD', '')})</span>
            </div>
            """
            
        tooltip_html = f"""
        <div style="font-family: sans-serif; padding: 8px; background: white; border-radius: 6px; box-shadow: 0 2px 10px rgba(0,0,0,0.2); width: 260px;">
            <div style="font-size: 12px; font-weight: bold; color: #555; margin-bottom: 4px; border-bottom: 2px solid #ddd; padding-bottom: 4px;">📍 이 위치의 매체 ({len(group)}개)</div>
            {tooltip_items_html}
        </div>
        """
        tooltip = folium.Tooltip(tooltip_html, parse_html=True)
        badge_html = '<div style="position: absolute; top: -10px; right: -16px; background-color: #e74c3c; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 3px; border: 1px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); z-index: 10;">불법</div>' if is_illegal else ''

        html_content = f"""
        <div style="position: relative; display: inline-block;">
            <div style="background-color: {bg_color}; width: 26px; height: 26px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 11px;">
                {len(group) if len(group) > 1 else '📍'}
            </div>
            {badge_html}
        </div>
        """
        folium.Marker(
            [lat, lon], 
            icon=folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16)),
            tooltip=tooltip
        ).add_to(m)
        
    return m

# 6. 고정 레이아웃 (7:3 분할로 튕김 100% 방지)
col_map, col_detail = st.columns([7, 3])

with col_map:
    map_obj = create_lightweight_map(len(map_data))
    # returned_objects=['last_clicked']를 통해 클릭만 감지하고 절대 튕기지 않음
    map_output = st_folium(map_obj, width="100%", height=850, returned_objects=['last_clicked'], key="main_map")
    
    # 클릭 즉시 좌표 갱신 (st.rerun 없이 바로 우측 패널에 데이터 반영)
    if map_output and map_output.get('last_clicked'):
        c_lat = map_output['last_clicked']['lat']
        c_lon = map_output['last_clicked']['lng']
        
        unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
        unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
        closest_idx = unique_coords['dist_sq'].idxmin()
        
        if unique_coords.loc[closest_idx, 'dist_sq'] < 0.0005: 
            st.session_state.clicked_lat = unique_coords.loc[closest_idx, 'LAT']
            st.session_state.clicked_lon = unique_coords.loc[closest_idx, 'LON']

# 7. 우측 상세 정보 패널 (여기서만 이미지를 동적으로 불러와 메모리를 아낍니다)
with col_detail:
    st.subheader("📋 매체 상세 정보")
    st.markdown("---")
    
    if st.session_state.clicked_lat is not None and st.session_state.clicked_lon is not None:
        matched = map_data[
            np.isclose(map_data['LAT'], st.session_state.clicked_lat, atol=1e-5) & 
            np.isclose(map_data['LON'], st.session_state.clicked_lon, atol=1e-5)
        ]
        
        if not matched.empty:
            for _, row in matched.iterrows():
                st.markdown(f"### 🏷️ {row.get('NAME', '')}")
                st.write(f"**유형:** {row.get('TYPE', '')}")
                st.write(f"**단가:** {row.get('PRICE', '')} 원 ({row.get('PERIOD', '')})")
                st.write(f"**합/불법:** {row.get('LEGAL', '')}")
                st.write(f"**주소:** {row.get('LOCATION', '')}")
                st.write(f"**상세:** {row.get('Details', '')}")
                
                # 우측 패널에서만 직접 이미지를 불러와서 렌더링
                try:
                    raw_id = row.get('ID', '')
                    id_str = str(raw_id).strip()
                    if id_str.endswith('.0'): id_str = id_str[:-2]
                    try:
                        id_str_z3, id_str_raw = str(int(float(id_str))).zfill(3), str(int(float(id_str)))
                    except:
                        id_str_z3, id_str_raw = id_str, id_str

                    found_images = False
                    if os.path.exists(IMAGE_DIR):
                        for f in os.listdir(IMAGE_DIR):
                            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                                name_no_ext = os.path.splitext(f)[0]
                                if name_no_ext in [f"{id_str_z3}_A", f"{id_str_raw}_A", f"{id_str_z3}_a", f"{id_str_raw}_a"]:
                                    img_path = os.path.join(IMAGE_DIR, f)
                                    st.markdown(f"**📸 대표 이미지**")
                                    st.image(img_path, use_container_width=True)
                                    found_images = True
                                    break
                    
                    if not found_images:
                        st.info("대표 이미지가 없습니다.")
                except Exception:
                    pass
                st.markdown("---")
    else:
        st.info("👈 지도에서 마커를 클릭하시면 이곳에 매체의 상세 정보와 이미지가 표시됩니다.")
