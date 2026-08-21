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

# 이미지 폴더 경로 (기본값: app.py와 같은 최상위 폴더)
user_img_dir = st.sidebar.text_input("이미지 폴더 경로 (비워두면 app.py와 같은 경로)", value="")

if not user_img_dir or user_img_dir == ".":
    IMAGE_DIR = BASE_DIR
elif os.path.isabs(user_img_dir):
    IMAGE_DIR = user_img_dir
else:
    IMAGE_DIR = os.path.join(BASE_DIR, user_img_dir)

# 1. 구글 시트 데이터 로드 (캐싱 적용)
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

# 2. 카카오 API 지오코딩 함수 (캐시 적용)
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

# 좌표 변환 수행
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
    st.warning("⚠️ 지도에 표시할 마커가 없습니다. 구글 시트의 `LOCATION`(주소) 컬럼명이나 카카오 API 키를 확인해 주세요!")

# Session State 초기화
if 'clicked_lat' not in st.session_state:
    st.session_state.clicked_lat = None
if 'clicked_lon' not in st.session_state:
    st.session_state.clicked_lon = None

# 비상용 사이드바 직접 선택 기능
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 매체 직접 선택")
media_names = ["선택 안 함"] + list(map_data['NAME'].astype(str).unique())
selected_media = st.sidebar.selectbox("매체명으로 바로 보기", media_names)

if selected_media != "선택 안 함":
    target_row = map_data[map_data['NAME'].astype(str) == selected_media].iloc[0]
    if st.session_state.clicked_lat != target_row['LAT'] or st.session_state.clicked_lon != target_row['LON']:
        st.session_state.clicked_lat = target_row['LAT']
        st.session_state.clicked_lon = target_row['LON']
        st.rerun()

# 💡 폴더 내 이미지 캐싱
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

# Folium 지도 생성 함수 (좌상단 범례 & 원상복구된 마커 컬러 규칙)
@st.cache_resource
def create_map(data_hash, img_dir):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 좌상단 가독성 좋은 범례
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
        
        # 마커 컬러 규칙 (LED, STATIC, LED + STATIC)
        if 'LED' in type_str and ('STATIC' in type_str or '+' in type_str):
            bg_color = '#9b59b6'  # 보라색
        elif 'LED' in type_str:
            bg_color = '#3498db'  # 파란색
        else:
            bg_color = '#2ecc71'  # 초록색
            
        is_illegal = any("불법" in str(val).replace(" ", "") for val in group['LEGAL'].values)
        
        # 동일 위치 다중 매체 호버링 지원
        tooltip_items_html = ""
        for _, row in group.iterrows():
            m_name = row.get('NAME', '')
            m_price = row.get('PRICE', '')
            m_period = row.get('PERIOD', '')
            thumb_b64 = find_thumbnail_for_id(row.get('ID', ''))
            
            tooltip_items_html += f"""
            <div style="border-bottom: 1px solid #eee; padding: 6px 0; text-align: left;">
                <b style="font-size: 13px; color: #111;">{m_name}</b><br>
                <span style="font-size: 12px; color: #e74c3c; font-weight: bold;">💰 {m_price} 원 ({m_period})</span>
                {f'<br><img src="data:image/jpeg;base64,{thumb_b64}" style="width:240px; height:160px; object-fit:cover; border-radius:6px; margin-top:6px; border:1px solid #ccc;" />' if thumb_b64 else ''}
            </div>
            """

        tooltip_html = f"""
        <div style="font-family: sans-serif; padding: 6px; background: white; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.35); max-height: 350px; overflow-y: auto; width: 280px;">
            <div style="font-size: 11px; font-weight: bold; color: #555; margin-bottom: 4px;">📍 이 위치의 매체 ({len(group)}개)</div>
            {tooltip_items_html}
        </div>
        """
        tooltip = folium.Tooltip(tooltip_html, parse_html=True)

        badge_html = ''
        if is_illegal:
            badge_html = '<div style="position: absolute; top: -10px; right: -16px; background-color: #e74c3c; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 3px; border: 1px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); z-index: 10;">불법</div>'

        html_content = f"""
        <div style="position: relative; display: inline-block; pointer-events: auto; cursor: pointer;">
            <div style="background-color: {bg_color}; width: 26px; height: 26px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 11px;">
                {len(group) if len(group) > 1 else '📍'}
            </div>
            {badge_html}
        </div>
        """
        
        custom_icon = folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16))
        
        folium.Marker(
            [lat, lon],
            icon=custom_icon,
            tooltip=tooltip
        ).add_to(m)
        
    return m

map_obj = create_map(len(map_data), IMAGE_DIR)

# 💡 고정 2분할 레이아웃 적용 (지도가 절대 다시 로딩되거나 줌이 리셋되지 않음)
col_map, col_detail = st.columns([3.8, 1.2])

with col_map:
    # 💡 returned_objects에서 center와 zoom을 제외하여 줌/팬 시 새로고침 원천 차단
    map_output = st_folium(
        map_obj, 
        width="100%", 
        height=800, 
        returned_objects=['last_clicked'],
        key="main_map"
    )
    
    if map_output and map_output.get('last_clicked'):
        c_lat = map_output['last_clicked']['lat']
        c_lon = map_output['last_clicked']['lng']
        
        unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
        unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
        closest = unique_coords.loc[unique_coords['dist_sq'].idxmin()]
        
        if st.session_state.clicked_lat != closest['LAT'] or st.session_state.clicked_lon != closest['LON']:
            st.session_state.clicked_lat = closest['LAT']
            st.session_state.clicked_lon = closest['LON']
            st.rerun()

with col_detail:
    if st.session_state.clicked_lat is not None:
        if st.button("❌ 상세 정보 닫기", use_container_width=True):
            st.session_state.clicked_lat = None
            st.session_state.clicked_lon = None
            st.rerun()
            
        st.subheader("📋 매체 상세 정보")
        
        matched = map_data[
            np.isclose(map_data['LAT'], st.session_state.clicked_lat, atol=1e-5) & 
            np.isclose(map_data['LON'], st.session_state.clicked_lon, atol=1e-5)
        ]
        
        if not matched.empty:
            st.success(f"선택하신 위치에 총 {len(matched)}개의 매체가 있습니다.")
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
                        if os.path.exists(IMAGE_DIR):
                            for f in os.listdir(IMAGE_DIR):
                                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                                    name_no_ext = os.path.splitext(f)[0]
                                    if name_no_ext == id_str_z3 or \
                                       name_no_ext == id_str_raw or \
                                       name_no_ext.startswith(id_str_z3 + '_') or \
                                       name_no_ext.startswith(id_str_raw + '_') or \
                                       name_no_ext.startswith(id_str_z3 + '-') or \
                                       name_no_ext.startswith(id_str_raw + '-'):
                                        matched_images.append(os.path.join(IMAGE_DIR, f))
                        
                        matched_images = sorted(list(set(matched_images)))
                        
                        if matched_images:
                            st.markdown(f"**📸 매체 이미지 ({len(matched_images)}장)**")
                            img_cols = st.columns(min(len(matched_images), 3))
                            for img_idx, img_path in enumerate(matched_images):
                                with img_cols[img_idx % 3]:
                                    try:
                                        img = Image.open(img_path)
                                        if img.mode != 'RGB':
                                            img = img.convert('RGB')
                                        st.image(img, use_container_width=True)
                                    except Exception as img_load_err:
                                        st.error(f"이미지 열기 실패: {os.path.basename(img_path)}")
                        else:
                            st.info(f"ID [{id_str_z3}]에 해당하는 이미지를 폴더에서 찾지 못했습니다.")
                    except Exception as e:
                        st.write(f"이미지 매핑 중 에러 발생: {e}")
                    
                    st.markdown("---")
        else:
            st.info("해당 위치의 매체 정보를 찾을 수 없습니다.")
    else:
        st.info("👈 좌측 지도에서 마커를 클릭하시면 상세 정보가 여기에 나타납니다.")
