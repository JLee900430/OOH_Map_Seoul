import streamlit as st
import pandas as pd
import requests
import io
import os
import glob
from streamlit_folium import st_folium
import folium

# 페이지 설정 (와이드 모드)
st.set_page_config(page_title="OOH Media Mix Dashboard", layout="wide")

st.title("🏙️ OOH Media Mix Dashboard (Auto-Mapping)")
st.markdown("이미지 폴더 주소만 입력하면, 시트의 `ID`와 파일명을 대조하여 모든 이미지가 자동으로 매핑되는 대시보드입니다.")

# 사이드바 환경 설정
st.sidebar.header("⚙️ 환경 설정")
KAKAO_API_KEY = st.sidebar.text_input("카카오 API 키", value="9f98264d7ef44f83084608ac07349c0b")
SHEET_URL = st.sidebar.text_input("구글 시트 CSV 링크", value="https://docs.google.com/spreadsheets/d/1mosGrKlMC4wggbf6VPjt3aQLm-R3WIPzVYbGoXVjeFY/export?format=csv&gid=1134856496")

# 사용자 환경에 맞는 기본 이미지 폴더 경로 지정 (필요 시 사이드바에서 수정 가능)
DEFAULT_IMG_DIR = os.path.expanduser("~/Desktop/이히리기우구추/AI/OOH_Map/image")
IMAGE_DIR = st.sidebar.text_input("이미지 폴더 경로", value=DEFAULT_IMG_DIR)

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

# 3. 레이아웃 분할 (좌측: 지도 / 우측: 상세 정보 패널)
col1, col2 = st.columns([1.5, 1])

with col1:
    st.subheader("📍 매체 위치 맵")
    # CartoDB Positron 모던 테마 적용
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 동일 좌표 그룹화 마커 생성
    for (lat, lon), group in map_data.groupby(['LAT', 'LON']):
        names = "<br>".join([f"• {name}" for name in group['NAME'].astype(str)])
        popup_html = f"<b>동일 위치 매체 ({len(group)}개)</b><br>{names}"
        
        folium.Marker(
            [lat, lon],
            tooltip=f"{group['NAME'].iloc[0]} 외 {len(group)-1}개" if len(group) > 1 else group['NAME'].iloc[0],
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(m)
    
    # Streamlit에서 Folium 지도 렌더링
    map_output = st_folium(m, width=700, height=600)

with col2:
    st.subheader("📋 매체 상세 정보")
    
    # 지도의 마커를 클릭했을 때 해당 좌표의 매체들을 우측에 리스트업
    if map_output and map_output.get('last_clicked'):
        clicked = map_output['last_clicked']
        lat_clicked, lon_clicked = clicked['lat'], clicked['lng']
        
        # 클릭한 위치와 가까운 매체 필터링 (소수점 4자리 오차 허용)
        matched = map_data[
            (map_data['LAT'].round(4) == round(lat_clicked, 4)) & 
            (map_data['LON'].round(4) == round(lon_clicked, 4))
        ]
        
        if not matched.empty:
            st.success(f"선택하신 위치에 총 {len(matched)}개의 매체가 있습니다.")
            for _, row in matched.iterrows():
                with st.container():
                    st.markdown(f"### 🏷️ {row.get('NAME', '')}")
                    st.write(f"**유형:** {row.get('TYPE', '')}")
                    st.write(f"**단가:** {row.get('PRICE', '')} 원")
                    st.write(f"**합/불법:** {row.get('LEGAL', '')}")
                    st.write(f"**주소:** {row.get('LOCATION', '')}")
                    st.write(f"**상세:** {row.get('Details', '')}")
                    
                    # 💡 ID를 바탕으로 폴더 안에서 이미지 파일 자동 매핑
                    try:
                        id_val = int(row['ID'])
                        id_str = str(id_val).zfill(3)
                        
                        # 001_1.jpg, 001_2.jpg 형태 및 1_*.jpg 형태 모두 탐색
                        search_pattern1 = os.path.join(IMAGE_DIR, f"{id_str}_*.*")
                        search_pattern2 = os.path.join(IMAGE_DIR, f"{id_val}_*.*")
                        
                        matched_images = glob.glob(search_pattern1) + glob.glob(search_pattern2)
                        matched_images = sorted(list(set(matched_images))) # 중복 제거 및 정렬
                        
                        if matched_images:
                            st.markdown(f"**📸 매체 이미지 ({len(matched_images)}장)**")
                            img_cols = st.columns(min(len(matched_images), 3))
                            for img_idx, img_path in enumerate(matched_images):
                                with img_cols[img_idx % 3]:
                                    st.image(img_path, use_container_width=True)
                        else:
                            st.info("해당 ID와 일치하는 이미지가 폴더에 없습니다.")
                    except Exception:
                        st.write("이미지 자동 매핑 중 에러가 발생했습니다.")
                    
                    st.markdown("---")
        else:
            st.info("해당 위치의 매체 정보를 찾을 수 없습니다.")
    else:
        st.info("👈 좌측 지도에서 마커를 클릭하시면 상세 정보와 이미지가 여기에 나타납니다.")
