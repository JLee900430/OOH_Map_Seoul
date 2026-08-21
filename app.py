import streamlit as st
import pandas as pd
import requests
import io
import os
import glob
from PIL import Image
from streamlit_folium import st_folium
import folium

# 페이지 설정 (와이드 모드)
st.set_page_config(page_title="OOH Media Mix Dashboard", layout="wide")

st.title("🏙️ OOH Media Mix Dashboard (Auto-Mapping)")
st.markdown("구글 시트 데이터와 폴더 내 이미지 파일명을 `ID`로 자동 매핑하여 보여주는 인터랙티브 미디어 믹스 맵입니다.")

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

# 디버깅용: 폴더 내 실제 이미지 파일 존재 여부 확인
with st.sidebar.expander("🔍 이미지 폴더 진단"):
    st.write(f"현재 인식된 절대 폴더 경로: `{IMAGE_DIR}`")
    if os.path.exists(IMAGE_DIR):
        found_files = os.listdir(IMAGE_DIR)
        st.success(f"폴더 안의 전체 파일 수: {len(found_files)}개")
        if len(found_files) > 0:
            st.write("샘플 파일명:", found_files[:5])
        else:
            st.warning("폴더는 존재하지만 안에 파일이 없습니다!")
    else:
        st.error("지정한 폴더 경로를 찾을 수 없습니다.")

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
    with st.sidebar.expander("🔍 구글 시트 진단"):
        st.write("불러온 컬럼 목록:", list(df.columns))
        st.write(f"전체 행 개수: {len(df)}개")
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

# Session State로 선택된 마커 위치 관리 (초기에는 None)
if 'clicked_lat' not in st.session_state:
    st.session_state.clicked_lat = None
if 'clicked_lon' not in st.session_state:
    st.session_state.clicked_lon = None

# Folium 지도 생성 공통 함수 (타입별 색상 및 불법 뱃지 아이콘 적용)
def create_map():
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    for (lat, lon), group in map_data.groupby(['LAT', 'LON']):
        # 1. 타입 분석 (LED, STATIC, LED + STATIC)
        types = group['TYPE'].astype(str).tolist()
        type_str = " ".join(types).upper()
        
        if 'LED' in type_str and ('STATIC' in type_str or '+' in type_str):
            bg_color = '#9b59b6'  # 보라색 (LED + STATIC)
        elif 'LED' in type_str:
            bg_color = '#3498db'  # 파란색 (LED)
        else:
            bg_color = '#2ecc71'  # 초록색 (STATIC)
            
        # 2. 불법 여부 확인 (LEGAL 컬럼에 '불법' 또는 'X' 등이 포함된 경우)
        is_illegal = any("불법" in str(val).replace(" ", "") for val in group['LEGAL'].values)
        
        # 3. 팝업 및 툴팁 텍스트 설정
        if len(group) > 1:
            names = "<br>".join([f"• {name}" for name in group['NAME'].astype(str)])
            popup_html = f"<b>동일 위치 매체 ({len(group)}개)</b><br>{names}"
            tooltip_text = f"{group['NAME'].iloc[0]} 외 {len(group)-1}개"
        else:
            name = group['NAME'].iloc[0]
            popup_html = f"<b>{name}</b>"
            tooltip_text = name

        # 4. 커스텀 HTML 아이콘 (DivIcon) 생성: 색상 원형 + 불법 뱃지
        badge_html = ''
        if is_illegal:
            badge_html = '<div style="position: absolute; top: -10px; right: -16px; background-color: #e74c3c; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 3px; border: 1px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); z-index: 10;">불법</div>'

        html_content = f"""
        <div style="position: relative; display: inline-block;">
            <div style="background-color: {bg_color}; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 10px;">
                {len(group) if len(group) > 1 else '📍'}
            </div>
            {badge_html}
        </div>
        """
        
        custom_icon = folium.DivIcon(
            html=html_content,
            icon_size=(30, 30),
            icon_anchor=(15, 15)
        )
        
        folium.Marker(
            [lat, lon],
            icon=custom_icon,
            tooltip=tooltip_text,
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(m)
        
    return m

# 3. 레이아웃 처리 (클릭 전: 전체화면 지도 / 클릭 후: 화면 분할)
if st.session_state.clicked_lat is None:
    st.subheader("📍 매체 위치 맵 (마커를 클릭하면 상세 정보가 나타납니다)")
    m = create_map()
    map_output = st_folium(m, width=1200, height=650, use_container_width=True)
    
    # 클릭 이벤트 감지 시 세션에 저장 후 리런
    if map_output:
        c_lat, c_lon = None, None
        if map_output.get('last_object_clicked'):
            c_lat = map_output['last_object_clicked']['lat']
            c_lon = map_output['last_object_clicked']['lng']
        elif map_output.get('last_clicked'):
            c_lat = map_output['last_clicked']['lat']
            c_lon = map_output['last_clicked']['lng']
        
        if c_lat is not None and c_lon is not None:
            st.session_state.clicked_lat = c_lat
            st.session_state.clicked_lon = c_lon
            st.rerun()
else:
    # 화면 분할 레이아웃 (좌측: 지도 / 우측: 상세 정보)
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        st.subheader("📍 매체 위치 맵")
        m = create_map()
        map_output = st_folium(m, width=700, height=600)
        
        # 분할 화면 상태에서도 다른 마커 클릭 시 정보 갱신
        if map_output:
            c_lat, c_lon = None, None
            if map_output.get('last_object_clicked'):
                c_lat = map_output['last_object_clicked']['lat']
                c_lon = map_output['last_object_clicked']['lng']
            elif map_output.get('last_clicked'):
                c_lat = map_output['last_clicked']['lat']
                c_lon = map_output['last_clicked']['lng']
            
            if c_lat is not None and c_lon is not None:
                if st.session_state.clicked_lat != c_lat or st.session_state.clicked_lon != c_lon:
                    st.session_state.clicked_lat = c_lat
                    st.session_state.clicked_lon = c_lon
                    st.rerun()

    with col2:
        st.subheader("📋 매체 상세 정보")
        
        matched = map_data[
            (map_data['LAT'].round(4) == round(st.session_state.clicked_lat, 4)) & 
            (map_data['LON'].round(4) == round(st.session_state.clicked_lon, 4))
        ]
        
        if not matched.empty:
            st.success(f"선택하신 위치에 총 {len(matched)}개의 매체가 있습니다.")
            for _, row in matched.iterrows():
                with st.container():
                    st.markdown(f"### 🏷️ {row.get('NAME', '')}")
                    st.write(f"**유형:** {row.get('TYPE', '')}")
                    st.write(f"**단가:** {row.get('PRICE', '')} 원")
                    st.write(f"**단가 기준:** {row.get('PERIOD', '')}")  # 단가 기준 (PERIOD) 정보
                    st.write(f"**합/불법:** {row.get('LEGAL', '')}")
                    st.write(f"**주소:** {row.get('LOCATION', '')}")
                    st.write(f"**상세:** {row.get('Details', '')}")
                    
                    # 💡 ID 매칭 및 PIL을 통한 안전한 이미지 로딩 (깨짐 방지 및 RGB 변환)
                    try:
                        raw_id = row.get('ID', '')
                        id_str = str(raw_id).strip()
                        if id_str.endswith('.0'):
                            id_str = id_str[:-2]
                        
                        try:
                            id_val = int(float(id_str))
                            id_str_z3 = str(id_val).zfill(3) # 예: 001
                            id_str_raw = str(id_val)         # 예: 1
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
