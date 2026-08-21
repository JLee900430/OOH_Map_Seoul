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

# Session State 초기화 (선택된 마커 및 지도 중심/줌 유지용)
if 'clicked_lat' not in st.session_state:
    st.session_state.clicked_lat = None
if 'clicked_lon' not in st.session_state:
    st.session_state.clicked_lon = None
if 'map_center' not in st.session_state:
    st.session_state.map_center = [37.5665, 126.9780]
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 11

# 비상용 사이드바 직접 선택 기능
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 매체 직접 선택 (비상용)")
media_names = ["선택 안 함"] + list(map_data['NAME'].astype(str).unique())
selected_media = st.sidebar.selectbox("매체명으로 바로 보기", media_names)

if selected_media != "선택 안 함":
    target_row = map_data[map_data['NAME'].astype(str) == selected_media].iloc[0]
    if st.session_state.clicked_lat != target_row['LAT'] or st.session_state.clicked_lon != target_row['LON']:
        st.session_state.clicked_lat = target_row['LAT']
        st.session_state.clicked_lon = target_row['LON']
        st.session_state.map_center = [target_row['LAT'], target_row['LON']]
        st.session_state.map_zoom = 14
        st.rerun()

# 💡 썸네일 변환 함수에 캐싱을 적용하여 속도를 극대화 (지연 시간 원천 차단)
@st.cache_data
def get_thumbnail_base64(img_dir, raw_id):
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

        if os.path.exists(img_dir):
            for f in os.listdir(img_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    name_no_ext = os.path.splitext(f)[0]
                    if name_no_ext == f"{id_str_z3}_A" or name_no_ext == f"{id_str_raw}_A" or \
                       name_no_ext == f"{id_str_z3}_a" or name_no_ext == f"{id_str_raw}_a":
                        img_path = os.path.join(img_dir, f)
                        with Image.open(img_path) as img:
                            img.thumbnail((600, 450))
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            buffered = BytesIO()
                            img.save(buffered, format="JPEG")
                            return base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        pass
    return None

# Folium 지도 생성 함수 (기억된 중심 좌표와 줌 레벨 반영)
def create_map(center, zoom):
    m = folium.Map(location=center, zoom_start=zoom, tiles='CartoDB positron')
    
    # 💡 '마커 컬러 의미' 행을 삭제한 깔끔한 범례
    legend_html = """
    <div style="position: fixed; 
                top: 15px; right: 15px; width: 145px; height: 80px; 
                background-color: white; z-index:9999; font-size:11px;
                border:2px solid grey; border-radius: 6px; padding: 8px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-family: sans-serif;">
      <div style="margin-top: 2px;"><span style="background:#3498db; width:10px; height:10px; display:inline-block; border-radius:50%; margin-right:5px;"></span> LED</div>
      <div style="margin-top: 4px;"><span style="background:#2ecc71; width:10px; height:10px; display:inline-block; border-radius:50%; margin-right:5px;"></span> STATIC</div>
      <div style="margin-top: 4px;"><span style="background:#9b59b6; width:10px; height:10px; display:inline-block; border-radius:50%; margin-right:5px;"></span> LED + STATIC</div>
      <div style="margin-top: 4px;"><span style="background:#e74c3c; width:10px; height:10px; display:inline-block; border-radius:3px; margin-right:5px;"></span> 불법 매체</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    
    for (lat, lon), group in map_data.groupby(['LAT', 'LON']):
        types = group['TYPE'].astype(str).tolist()
        type_str = " ".join(types).upper()
        
        is_illegal = any("불법" in str(val).replace(" ", "") for val in group['LEGAL'].values)
        
        if is_illegal:
            marker_color = 'red'
        elif 'LED' in type_str and ('STATIC' in type_str or '+' in type_str):
            marker_color = 'purple'
        elif 'LED' in type_str:
            marker_color = 'blue'
        else:
            marker_color = 'green'
            
        first_row = group.iloc[0]
        thumb_b64 = get_thumbnail_base64(IMAGE_DIR, first_row.get('ID', ''))
        
        if len(group) > 1:
            tooltip_title = f"{first_row['NAME']} 외 {len(group)-1}개"
        else:
            tooltip_title = first_row['NAME']

        price_val = first_row.get('PRICE', '')
        period_val = first_row.get('PERIOD', '')

        # 대폭 확대된 300% 호버링 프리뷰 (가격, 단가 기준, ID_A 이미지 포함)
        tooltip_html = f"""
        <div style="text-align: center; font-family: sans-serif; padding: 10px; background: white; border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,0.35); width: 320px;">
            <b style="font-size: 16px; color: #111;">{tooltip_title}</b><br>
            <div style="font-size: 13px; color: #e74c3c; font-weight: bold; margin-top: 6px;">💰 {price_val} 원 ({period_val})</div>
            {f'<img src="data:image/jpeg;base64,{thumb_b64}" style="width:300px; height:220px; object-fit:cover; border-radius:8px; margin-top:8px; border:1px solid #ccc;" />' if thumb_b64 else '<div style="font-size:12px; color:#888; margin-top:6px;">대표 이미지(ID_A) 없음</div>'}
        </div>
        """
        tooltip = folium.Tooltip(tooltip_html, parse_html=True)

        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color=marker_color, icon='info-sign', prefix='glyphicon'),
            tooltip=tooltip
        ).add_to(m)
        
    return m

# 공통 클릭 및 상태 업데이트 처리 함수
def handle_map_output(map_output):
    if map_output:
        # 지도 중심과 줌 상태 업데이트 저장
        if 'center' in map_output and map_output['center']:
            st.session_state.map_center = [map_output['center']['lat'], map_output['center']['lng']]
        if 'zoom' in map_output and map_output['zoom']:
            st.session_state.map_zoom = map_output['zoom']

        # 마커 클릭 감지
        clicked_obj = map_output.get('last_object_clicked')
        if clicked_obj and 'lat' in clicked_obj and 'lng' in clicked_obj:
            c_lat = clicked_obj['lat']
            c_lon = clicked_obj['lng']
            
            unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
            unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
            closest = unique_coords.loc[unique_coords['dist_sq'].idxmin()]
            
            if st.session_state.clicked_lat != closest['LAT'] or st.session_state.clicked_lon != closest['LON']:
                st.session_state.clicked_lat = closest['LAT']
                st.session_state.clicked_lon = closest['LON']
                st.rerun()

# 💡 동적 레이아웃: 초기에는 전체화면 지도, 마커 클릭 시에만 2분할 뷰 전환
if st.session_state.clicked_lat is None:
    m = create_map(st.session_state.map_center, st.session_state.map_zoom)
    map_output = st_folium(
        m, 
        width=1300, 
        height=750, 
        returned_objects=['last_object_clicked', 'center', 'zoom'],
        key="full_map"
    )
    handle_map_output(map_output)

else:
    col1, col2 = st.columns([1.6, 1])
    
    with col1:
        m = create_map(st.session_state.map_center, st.session_state.map_zoom)
        map_output = st_folium(
            m, 
            width=700, 
            height=680, 
            returned_objects=['last_object_clicked', 'center', 'zoom'],
            key="split_map"
        )
        handle_map_output(map_output)

    with col2:
        st.subheader("📋 매체 상세 정보")
        
        if st.button("❌ 상세 정보 닫기 (지도 전체보기)", use_container_width=True):
            st.session_state.clicked_lat = None
            st.session_state.clicked_lon = None
            st.rerun()
            
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
