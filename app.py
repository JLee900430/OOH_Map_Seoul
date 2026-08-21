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

# 1. 페이지 설정 (와이드 모드)
st.set_page_config(page_title="OOH Media in SEOUL", layout="wide")
st.title("🏙️ OOH Media in SEOUL")

# 2. 경로 및 환경 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
st.sidebar.header("⚙️ 환경 설정")
KAKAO_API_KEY = st.sidebar.text_input("카카오 API 키", value="9f98264d7ef44f83084608ac07349c0b")
SHEET_URL = st.sidebar.text_input("구글 시트 CSV 링크", value="https://docs.google.com/spreadsheets/d/1mosGrKlMC4wggbf6VPjt3aQLm-R3WIPzVYbGoXVjeFY/export?format=csv&gid=1134856496")
user_img_dir = st.sidebar.text_input("이미지 폴더 경로 (비워두면 app.py와 같은 경로)", value="")

IMAGE_DIR = user_img_dir if (user_img_dir and os.path.isabs(user_img_dir)) else (os.path.join(BASE_DIR, user_img_dir) if user_img_dir and user_img_dir != "." else BASE_DIR)

# 3. 데이터 로드 및 지오코딩 (캐싱)
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
    with st.spinner("최초 1회 주소 좌표 변환 중..."):
        df['LAT'], df['LON'] = zip(*df['LOCATION'].apply(lambda x: get_lat_lon(x, KAKAO_API_KEY)))

map_data = df.dropna(subset=['LAT', 'LON'])
if len(map_data) == 0:
    st.warning("⚠️ 지도에 표시할 마커가 없습니다.")

# 4. 이미지 캐싱 및 썸네일 생성 (속도 최적화)
@st.cache_data
def build_image_map(img_dir):
    img_map = {}
    if os.path.exists(img_dir):
        for f in os.listdir(img_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                img_map[os.path.splitext(f)[0]] = os.path.join(img_dir, f)
    return img_map

IMAGE_MAP = build_image_map(IMAGE_DIR)

@st.cache_data
def get_thumbnail_base64(img_path):
    try:
        if img_path and os.path.exists(img_path):
            with Image.open(img_path) as img:
                img.thumbnail((300, 225))
                if img.mode != 'RGB': img = img.convert('RGB')
                buffered = BytesIO()
                img.save(buffered, format="JPEG", quality=60)
                return base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        pass
    return None

def find_thumbnail_for_id(raw_id):
    id_str = str(raw_id).strip()
    if id_str.endswith('.0'): id_str = id_str[:-2]
    try:
        id_val = int(float(id_str))
        id_str_z3, id_str_raw = str(id_val).zfill(3), str(id_val)
    except:
        id_str_z3, id_str_raw = id_str, id_str

    for candidate in [f"{id_str_z3}_A", f"{id_str_raw}_A", f"{id_str_z3}_a", f"{id_str_raw}_a"]:
        if candidate in IMAGE_MAP:
            return get_thumbnail_base64(IMAGE_MAP[candidate])
    return None

# 5. 지도 생성 (호버링 완벽 복구, 튕김 원천 차단)
@st.cache_resource
def create_map(data_hash, img_dir):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 좌상단 타이틀 & 범례
    title_legend_html = """
    <div style="position: fixed; top: 15px; left: 60px; width: 220px; height: 135px; background-color: white; z-index:9999; font-size:12px; border:2px solid #ccc; border-radius: 8px; padding: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-family: sans-serif; line-height: 1.5;">
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
        bg_color = '#9b59b6' if 'LED' in type_str and ('STATIC' in type_str or '+' in type_str) else ('#3498db' if 'LED' in type_str else '#2ecc71')
        is_illegal = any("불법" in str(val).replace(" ", "") for val in group['LEGAL'].values)
        
        # 정석적인 2x2 그리드 동적 프리뷰
        tooltip_items_html = ""
        for _, row in group.iterrows():
            thumb_b64 = find_thumbnail_for_id(row.get('ID', ''))
            tooltip_items_html += f"""
            <div style="background: #fdfdfd; border: 1px solid #e0e0e0; padding: 6px; border-radius: 6px; text-align: left;">
                <b style="font-size: 13px; color: #111;">{row.get('NAME', '')}</b><br>
                <span style="font-size: 11px; color: #e74c3c; font-weight: bold;">💰 {row.get('PRICE', '')} 원 ({row.get('PERIOD', '')})</span>
                {f'<br><img src="data:image/jpeg;base64,{thumb_b64}" style="width:100%; height:120px; object-fit:cover; border-radius:4px; margin-top:4px; border:1px solid #ccc;" />' if thumb_b64 else '<div style="font-size:10px; color:#888; margin-top:4px;">이미지 없음</div>'}
            </div>
            """
            
        grid_cols = "repeat(2, 1fr)" if len(group) > 1 else "1fr"
        container_width = "520px" if len(group) > 1 else "280px"
        tooltip_html = f"""
        <div style="font-family: sans-serif; padding: 8px; background: white; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.35); width: {container_width};">
            <div style="font-size: 12px; font-weight: bold; color: #555; margin-bottom: 6px; border-bottom: 2px solid #ddd; padding-bottom: 4px;">📍 이 위치의 매체 ({len(group)}개)</div>
            <div style="display: grid; grid-template-columns: {grid_cols}; gap: 8px;">{tooltip_items_html}</div>
        </div>
        """
        tooltip = folium.Tooltip(tooltip_html, parse_html=True)
        badge_html = '<div style="position: absolute; top: -10px; right: -16px; background-color: #e74c3c; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 3px; border: 1px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); z-index: 10;">불법</div>' if is_illegal else ''

        # 깔끔하고 안정적인 단일 마커 구조
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

map_obj = create_map(len(map_data), IMAGE_DIR)

# 6. 고정 레이아웃 렌더링 (지도가 튕기지 않는 가장 확실한 방법)
# 좌측에 매우 넓은 지도 영역, 우측에 상세 정보 영역 고정 배치
col_map, col_detail = st.columns([7, 3])

with col_map:
    # returned_objects=['last_object_clicked'] 설정으로 줌/패닝 시 새로고침 방지
    map_output = st_folium(
        map_obj, 
        width="100%", 
        height=850, 
        returned_objects=['last_object_clicked'], 
        key="main_stable_map"
    )

# 7. 클릭 이벤트 처리 (st.rerun 없이 자연스럽게 UI 갱신)
clicked_lat, clicked_lon = None, None

if map_output and map_output.get('last_object_clicked'):
    c_lat = map_output['last_object_clicked']['lat']
    c_lon = map_output['last_object_clicked']['lng']
    
    unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
    unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
    closest_idx = unique_coords['dist_sq'].idxmin()
    
    # 허용 오차 내의 마커 클릭만 유효하게 처리
    if unique_coords.loc[closest_idx, 'dist_sq'] < 0.0005: 
        clicked_lat = unique_coords.loc[closest_idx, 'LAT']
        clicked_lon = unique_coords.loc[closest_idx, 'LON']

# 8. 우측 상세 정보 패널 출력
with col_detail:
    st.subheader("📋 매체 상세 정보")
    st.markdown("---")
    
    if clicked_lat is not None and clicked_lon is not None:
        matched = map_data[
            np.isclose(map_data['LAT'], clicked_lat, atol=1e-5) & 
            np.isclose(map_data['LON'], clicked_lon, atol=1e-5)
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
                    
                    # 팝업 내부 고화질 이미지 매칭
                    try:
                        raw_id = row.get('ID', '')
                        id_str = str(raw_id).strip()
                        if id_str.endswith('.0'): id_str = id_str[:-2]
                        try:
                            id_str_z3, id_str_raw = str(int(float(id_str))).zfill(3), str(int(float(id_str)))
                        except:
                            id_str_z3, id_str_raw = id_str, id_str

                        matched_images = []
                        for candidate in [f"{id_str_z3}_A", f"{id_str_raw}_A", f"{id_str_z3}_a", f"{id_str_raw}_a"]:
                            if candidate in IMAGE_MAP:
                                matched_images.append(IMAGE_MAP[candidate])
                        
                        if matched_images:
                            st.markdown(f"**📸 대표 이미지**")
                            for img_path in sorted(list(set(matched_images))):
                                try:
                                    img = Image.open(img_path)
                                    if img.mode != 'RGB': img = img.convert('RGB')
                                    st.image(img, use_container_width=True)
                                except Exception:
                                    pass
                        else:
                            st.info("대표 이미지가 없습니다.")
                    except Exception:
                        pass
                    st.markdown("---")
    else:
        st.info("👈 지도에서 마커를 클릭하시면 이곳에 상세 정보가 즉시 표시됩니다.")
