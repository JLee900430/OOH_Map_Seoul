import streamlit as st
import pandas as pd
import requests
import io
import os
import glob
import base64
import numpy as np
from io import BytesIO
from PIL import Image
from streamlit_folium import st_folium
import folium

# 페이지 설정 (와이드 모드)
st.set_page_config(page_title="OOH Media in SEOUL", layout="wide")

# 타이틀 설정
st.title("🏙️ OOH Media in SEOUL")

# 0. app.py가 위치한 절대 경로를 기준으로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 사이드바 환경 설정
st.sidebar.header("⚙️ 환경 설정")
KAKAO_API_KEY = st.sidebar.text_input("카카오 API 키", value="9f98264d7ef44f83084608ac07349c0b")
SHEET_URL = st.sidebar.text_input("구글 시트 CSV 링크", value="https://docs.google.com/spreadsheets/d/1mosGrKlMC4wggbf6VPjt3aQLm-R3WIPzVYbGoXVjeFY/export?format=csv&gid=1134856496")

user_img_dir = st.sidebar.text_input("이미지 폴더 경로 (비워두면 app.py와 같은 경로)", value="")

if not user_img_dir or user_img_dir == ".":
    IMAGE_DIR = BASE_DIR
elif os.path.isabs(user_img_dir):
    IMAGE_DIR = user_img_dir
else:
    IMAGE_DIR = os.path.join(BASE_DIR, user_img_dir)

# 1. 구글 시트 데이터 로드 (캐싱)
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

# 2. 카카오 API 지오코딩 함수 (캐싱)
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
    with st.spinner("주소를 좌표로 변환하는 중입니다... (최초 1회만 진행됩니다)"):
        lats, lons = [], []
        for addr in df['LOCATION']:
            lat, lon = get_lat_lon(addr, KAKAO_API_KEY)
            lats.append(lat)
            lons.append(lon)
        df['LAT'] = lats
        df['LON'] = lons

map_data = df.dropna(subset=['LAT', 'LON'])

if len(map_data) == 0:
    st.warning("⚠️ 지도에 표시할 마커가 없습니다.")

# Session State 초기화
if 'clicked_lat' not in st.session_state:
    st.session_state.clicked_lat = None
if 'clicked_lon' not in st.session_state:
    st.session_state.clicked_lon = None

# 이미지 폴더 1회 스캔 캐싱 (속도 극대화)
@st.cache_data
def build_image_map(img_dir):
    img_map = {}
    if os.path.exists(img_dir):
        for f in os.listdir(img_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                name_no_ext = os.path.splitext(f)[0]
                img_map[name_no_ext] = os.path.join(img_dir, f)
    return img_map

IMAGE_MAP = build_image_map(IMAGE_DIR)

@st.cache_data
def get_thumbnail_base64(img_path):
    try:
        if img_path and os.path.exists(img_path):
            with Image.open(img_path) as img:
                img.thumbnail((400, 300))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                return base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        pass
    return None

def find_thumbnail_for_id(raw_id):
    try:
        id_str = str(raw_id).strip()
        if id_str.endswith('.0'):
            id_str = id_str[:-2]
        try:
            id_val = int(float(id_str))
            id_str_z3 = str(id_val).zfill(3)
            id_str_raw = str(id_val)
        except:
            id_str_z3 = id_str
            id_str_raw = id_str

        for candidate in [f"{id_str_z3}_A", f"{id_str_raw}_A", f"{id_str_z3}_a", f"{id_str_raw}_a"]:
            if candidate in IMAGE_MAP:
                return get_thumbnail_base64(IMAGE_MAP[candidate])
    except Exception:
        pass
    return None

# 💡 지도 생성 함수 캐싱 (최초 1회만 로딩)
@st.cache_resource
def create_map(data_hash, img_dir):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 좌상단 타이틀 & 범례
    title_legend_html = """
    <div style="position: fixed; 
                top: 15px; left: 60px; width: 220px; height: 135px; 
                background-color: white; z-index:9999; font-size:12px;
                border:2px solid #ccc; border-radius: 8px; padding: 10px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-family: sans-serif; line-height: 1.5;">
      <b style="font-size: 14px; color: #111;">🏙️ OOH Media in SEOUL</b><hr style="margin: 5px 0; border:0; border-top:1px solid #eee;">
      <div><span style="background:#3498db; width:12px; height:12px; display:inline-block; border-radius:50%; margin-right:6px; vertical-align: middle;"></span> LED</div>
      <div><span style="background:#2ecc71; width:12px; height:12px; display:inline-block; border-radius:50%; margin-right:6px; vertical-align: middle;"></span> STATIC</div>
      <div><span style="background:#9b59b6; width:12px; height:12px; display:inline-block; border-radius:50%; margin-right:6px; vertical-align: middle;"></span> LED + STATIC</div>
      <div><span style="background:#e74c3c; width:12px; height:12px; display:inline-block; border-radius:3px; margin-right:6px; vertical-align: middle;"></span> 불법 매체</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_legend_html))
    
    for (lat, lon), group in map_data.groupby(['LAT', 'LON']):
        types = group['TYPE'].astype(str).tolist()
        type_str = " ".join(types).upper()
        
        # 마커 색상 규칙
        if 'LED' in type_str and ('STATIC' in type_str or '+' in type_str):
            bg_color = '#9b59b6'
        elif 'LED' in type_str:
            bg_color = '#3498db'
        else:
            bg_color = '#2ecc71'
            
        is_illegal = any("불법" in str(val).replace(" ", "") for val in group['LEGAL'].values)
        
        # 2x2 그리드 동적 프리뷰 유지
        tooltip_items_html = ""
        for _, row in group.iterrows():
            m_name = row.get('NAME', '')
            m_price = row.get('PRICE', '')
            m_period = row.get('PERIOD', '')
            thumb_b64 = find_thumbnail_for_id(row.get('ID', ''))
            
            tooltip_items_html += f"""
            <div style="background: #fdfdfd; border: 1px solid #e0e0e0; padding: 8px; border-radius: 6px; text-align: left;">
                <b style="font-size: 13px; color: #111;">{m_name}</b><br>
                <span style="font-size: 11px; color: #e74c3c; font-weight: bold;">💰 {m_price} 원 ({m_period})</span>
                {f'<br><img src="data:image/jpeg;base64,{thumb_b64}" style="width:100%; height:130px; object-fit:cover; border-radius:4px; margin-top:6px; border:1px solid #ccc;" />' if thumb_b64 else '<div style="font-size:10px; color:#888; margin-top:4px;">이미지 없음</div>'}
            </div>
            """

        grid_cols = "repeat(2, 1fr)" if len(group) > 1 else "1fr"
        container_width = "520px" if len(group) > 1 else "280px"

        tooltip_html = f"""
        <div style="font-family: sans-serif; padding: 8px; background: white; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.35); width: {container_width};">
            <div style="font-size: 12px; font-weight: bold; color: #555; margin-bottom: 6px; border-bottom: 2px solid #ddd; padding-bottom: 4px;">📍 이 위치의 매체 ({len(group)}개)</div>
            <div style="display: grid; grid-template-columns: {grid_cols}; gap: 8px;">
                {tooltip_items_html}
            </div>
        </div>
        """
        tooltip = folium.Tooltip(tooltip_html, parse_html=True)

        badge_html = ''
        if is_illegal:
            badge_html = '<div style="position: absolute; top: -10px; right: -16px; background-color: #e74c3c; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 3px; border: 1px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); z-index: 10;">불법</div>'

        # 💡 [핵심 기술 1] 디자인 HTML 요소는 마우스 이벤트(클릭)를 무시하도록 pointer-events: none 적용
        html_content = f"""
        <div style="position: relative; pointer-events: none;">
            <div style="background-color: {bg_color}; width: 26px; height: 26px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 11px;">
                {len(group) if len(group) > 1 else '📍'}
            </div>
            {badge_html}
        </div>
        """
        custom_icon = folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16))
        
        # 디자인용 마커 렌더링 (호버링 툴팁 없음)
        folium.Marker([lat, lon], icon=custom_icon).add_to(m)
        
        # 💡 [핵심 기술 2] 투명한 CircleMarker를 덮어씌워 100% 확률로 클릭과 호버링 이벤트를 낚아챔
        folium.CircleMarker(
            location=[lat, lon],
            radius=16,
            stroke=False,
            fill=True,
            fill_opacity=0.0, # 완벽히 투명함
            tooltip=tooltip
        ).add_to(m)
        
    return m

map_obj = create_map(len(map_data), IMAGE_DIR)

# 💡 [핵심 기술 3] 분할 레이아웃 폐기: 지도를 항상 전체화면으로 고정하여 줌 풀림 및 로딩 지연 원천 차단
map_output = st_folium(
    map_obj, 
    width="100%", 
    height=850, 
    returned_objects=['last_object_clicked'], # 오직 클릭만 감지 (줌/이동 시 리렌더링 방지)
    key="main_fullscreen_map"
)

# 💡 [핵심 기술 4] st.rerun() 제거: Streamlit 자체 동작을 활용하여 더블 로딩 지연 현상 방지
if map_output and map_output.get('last_object_clicked'):
    c_lat = map_output['last_object_clicked']['lat']
    c_lon = map_output['last_object_clicked']['lng']
    
    unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
    unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
    closest = unique_coords.loc[unique_coords['dist_sq'].idxmin()]
    
    st.session_state.clicked_lat = closest['LAT']
    st.session_state.clicked_lon = closest['LON']

# 우측 오버레이(팝업) 애니메이션 패널
if st.session_state.clicked_lat is not None:
    with st.container():
        st.markdown('<span class="drawer-marker"></span>', unsafe_allow_html=True)
        st.markdown("""
        <style>
        div[data-testid="stVerticalBlock"]:has(> div.element-container .drawer-marker):not(:has(div[data-testid="stVerticalBlock"] .drawer-marker)) {
            position: fixed !important;
            top: 0 !important;
            right: 0 !important;
            width: 550px !important;
            max-width: 90vw !important;
            height: 100vh !important;
            background-color: #fcfcfc !important;
            z-index: 999999 !important;
            box-shadow: -8px 0 30px rgba(0,0,0,0.3) !important;
            padding: 3rem 2.5rem !important;
            overflow-y: auto !important;
            animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
        }
        @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        </style>
        """, unsafe_allow_html=True)
        
        col_btn, col_title = st.columns([1, 4])
        with col_btn:
            if st.button("❌ 닫기", use_container_width=True, key="close_overlay"):
                st.session_state.clicked_lat = None
                st.session_state.clicked_lon = None
                st.rerun()
        with col_title:
            st.subheader("📋 매체 상세 정보")
            
        st.markdown("---")
        
        matched = map_data[
            np.isclose(map_data['LAT'], st.session_state.clicked_lat, atol=1e-5) & 
            np.isclose(map_data['LON'], st.session_state.clicked_lon, atol=1e-5)
        ]
        
        if not matched.empty:
            for _, row in matched.iterrows():
                with st.container():
                    st.markdown(f"### 🏷️ {row.get('NAME', '')}")
                    st.write(f"**유형:** {row.get('TYPE', '')}")
                    st.write(f"**단가:** {row.get('PRICE', '')} 원")
                    st.write(f"**단가 기준:** {row.get('PERIOD', '')}")
                    st.write(f"**합/불법:** {row.get('LEGAL', '')}")
                    st.write(f"**주소:** {row.get('LOCATION', '')}")
                    st.write(f"**상세:** {row.get('Details', '')}")
                    
                    try:
                        raw_id = row.get('ID', '')
                        id_str = str(raw_id).strip()
                        if id_str.endswith('.0'):
                            id_str = id_str[:-2]
                        
                        try:
                            id_val = int(float(id_str))
                            id_str_z3 = str(id_val).zfill(3)
                            id_str_raw = str(id_val)
                        except:
                            id_str_z3 = id_str
                            id_str_raw = id_str

                        matched_images = []
                        for candidate in [f"{id_str_z3}_A", f"{id_str_raw}_A", f"{id_str_z3}_a", f"{id_str_raw}_a"]:
                            if candidate in IMAGE_MAP:
                                matched_images.append(IMAGE_MAP[candidate])
                        
                        matched_images = sorted(list(set(matched_images)))
                        
                        if matched_images:
                            st.markdown(f"**📸 대표 이미지**")
                            for img_path in matched_images:
                                try:
                                    img = Image.open(img_path)
                                    if img.mode != 'RGB':
                                        img = img.convert('RGB')
                                    st.image(img, use_container_width=True)
                                except Exception as img_load_err:
                                    st.error(f"이미지 열기 실패: {os.path.basename(img_path)}")
                        else:
                            st.info("대표 이미지가 없습니다.")
                    except Exception as e:
                        st.write(f"이미지 매핑 에러: {e}")
                    
                    st.markdown("---")
