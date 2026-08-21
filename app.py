import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from streamlit_folium import st_folium
import folium

# 1. 페이지 및 레이아웃 설정 (튕김 방지 7:3 고정 레이아웃 적용)
st.set_page_config(page_title="OOH Media in SEOUL", layout="wide")
st.title("🏙️ OOH Media in SEOUL")

# 2. 사이드바 설정 (GitHub URL 입력칸 마련)
st.sidebar.header("⚙️ 환경 설정")
KAKAO_API_KEY = st.sidebar.text_input("카카오 API 키", value="9f98264d7ef44f83084608ac07349c0b")
SHEET_URL = st.sidebar.text_input("구글 시트 CSV 링크", value="https://docs.google.com/spreadsheets/d/1mosGrKlMC4wggbf6VPjt3aQLm-R3WIPzVYbGoXVjeFY/export?format=csv&gid=1134856496")

st.sidebar.markdown("---")
st.sidebar.subheader("🔗 GitHub 이미지 연동")
st.sidebar.write("GitHub Raw URL을 입력하면 메모리 에러 없이 초고속으로 이미지가 로드됩니다.")
# 예시: https://raw.githubusercontent.com/username/repo/main/images/
github_base_url = st.sidebar.text_input("GitHub 이미지 기본 URL", value="")

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
    st.error(f"데이터 로드 실패: {e}")
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
    with st.spinner("최초 1회 좌표 변환 중..."):
        df['LAT'], df['LON'] = zip(*df['LOCATION'].apply(lambda x: get_lat_lon(x, KAKAO_API_KEY)))

map_data = df.dropna(subset=['LAT', 'LON'])
if len(map_data) == 0:
    st.warning("⚠️ 지도에 표시할 마커가 없습니다.")

# 클릭 상태 초기화
if 'clicked_lat' not in st.session_state:
    st.session_state.clicked_lat = None
if 'clicked_lon' not in st.session_state:
    st.session_state.clicked_lon = None

# ID 기반 GitHub URL 생성 함수 (예: 001_A.jpg)
def get_github_image_url(raw_id, base_url):
    if not base_url: return None
    try:
        id_str = str(raw_id).strip()
        if id_str.endswith('.0'): id_str = id_str[:-2]
        id_str_z3 = str(int(float(id_str))).zfill(3)
        if not base_url.endswith('/'): base_url += '/'
        return f"{base_url}{id_str_z3}_A.jpg"
    except Exception:
        return None

# 4. 지도 생성 (메모리 0%, GitHub 링크 기반 2x2 호버링)
@st.cache_resource
def create_map(data_hash, base_url):
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11, tiles='CartoDB positron')
    
    # 우상단 범례
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
        
        # 💡 GitHub 이미지 URL을 활용한 2x2 호버링 프리뷰
        tooltip_items_html = ""
        for _, row in group.iterrows():
            m_name, m_price, m_period = row.get('NAME', ''), row.get('PRICE', ''), row.get('PERIOD', '')
            img_url = get_github_image_url(row.get('ID', ''), base_url)
            
            # 이미지가 깨질 경우(404 에러 등)를 대비한 onerror 처리
            img_tag = f'<br><img src="{img_url}" style="width:100%; height:110px; object-fit:cover; border-radius:4px; margin-top:6px; border:1px solid #ccc;" onerror="this.style.display=\'none\'" />' if img_url else ''
            
            tooltip_items_html += f"""
            <div style="background: #fdfdfd; border: 1px solid #e0e0e0; padding: 8px; border-radius: 6px; text-align: left;">
                <b style="font-size: 13px; color: #111;">{m_name}</b><br>
                <span style="font-size: 11px; color: #e74c3c; font-weight: bold;">💰 {m_price} 원 ({m_period})</span>
                {img_tag}
            </div>
            """

        grid_cols = "repeat(2, 1fr)" if len(group) > 1 else "1fr"
        container_width = "480px" if len(group) > 1 else "240px"

        tooltip_html = f"""
        <div style="font-family: sans-serif; padding: 8px; background: white; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.35); width: {container_width};">
            <div style="font-size: 12px; font-weight: bold; color: #555; margin-bottom: 6px; border-bottom: 2px solid #ddd; padding-bottom: 4px;">📍 이 위치의 매체 ({len(group)}개)</div>
            <div style="display: grid; grid-template-columns: {grid_cols}; gap: 8px;">
                {tooltip_items_html}
            </div>
        </div>
        """
        tooltip = folium.Tooltip(tooltip_html, parse_html=True)
        badge_html = '<div style="position: absolute; top: -10px; right: -16px; background-color: #e74c3c; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 3px; border: 1px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); z-index: 10;">불법</div>' if is_illegal else ''

        # 💡 시각용 마커 (이벤트 무시: pointer-events: none)
        html_content = f"""
        <div style="position: relative; display: inline-block; pointer-events: none;">
            <div style="background-color: {bg_color}; width: 26px; height: 26px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 11px;">
                {len(group) if len(group) > 1 else '📍'}
            </div>
            {badge_html}
        </div>
        """
        folium.Marker([lat, lon], icon=folium.DivIcon(html=html_content, icon_size=(32, 32), icon_anchor=(16, 16))).add_to(m)
        
        # 💡 클릭 및 호버링 전용 투명 마커 (클릭 씹힘 완벽 방어)
        folium.CircleMarker(
            location=[lat, lon], radius=14, color=None, fill=True, fill_color='white', fill_opacity=0.0, tooltip=tooltip
        ).add_to(m)
        
    return m

map_obj = create_map(len(map_data), github_base_url)

# 5. 고정 레이아웃 (지도 튕김 원천 차단)
col_map, col_detail = st.columns([7, 3])

with col_map:
    # 💡 returned_objects=['last_clicked'] 설정으로 드래그/줌아웃 시 새로고침 방지
    map_output = st_folium(
        map_obj, 
        width="100%", 
        height=850, 
        returned_objects=['last_clicked'], 
        key="main_stable_map"
    )

# 6. 스마트 클릭 감지 (st.rerun 없이 즉시 렌더링)
if map_output and map_output.get('last_clicked'):
    c_lat, c_lon = map_output['last_clicked']['lat'], map_output['last_clicked']['lng']
    unique_coords = map_data[['LAT', 'LON']].drop_duplicates().copy()
    unique_coords['dist_sq'] = (unique_coords['LAT'] - c_lat)**2 + (unique_coords['LON'] - c_lon)**2
    closest_idx = unique_coords['dist_sq'].idxmin()
    
    if unique_coords.loc[closest_idx, 'dist_sq'] < 0.0005: 
        st.session_state.clicked_lat = unique_coords.loc[closest_idx, 'LAT']
        st.session_state.clicked_lon = unique_coords.loc[closest_idx, 'LON']

# 7. 우측 상세 정보 패널
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
                with st.container():
                    st.markdown(f"### 🏷️ {row.get('NAME', '')}")
                    st.write(f"**유형:** {row.get('TYPE', '')}")
                    st.write(f"**단가:** {row.get('PRICE', '')} 원 ({row.get('PERIOD', '')})")
                    st.write(f"**합/불법:** {row.get('LEGAL', '')}")
                    st.write(f"**주소:** {row.get('LOCATION', '')}")
                    st.write(f"**상세:** {row.get('Details', '')}")
                    
                    # 상세창에서도 GitHub 이미지 URL 직접 로드
                    img_url = get_github_image_url(row.get('ID', ''), github_base_url)
                    if img_url:
                        st.markdown(f"**📸 대표 이미지**")
                        st.markdown(f'<img src="{img_url}" style="width:100%; border-radius:8px; border:1px solid #ccc;" onerror="this.style.display=\'none\'" />', unsafe_allow_html=True)
                    else:
                        st.info("사이드바에 GitHub URL을 입력하시면 이미지가 표시됩니다.")
                    
                    st.markdown("---")
    else:
        st.info("👈 지도에서 마커를 클릭하시면 이곳에 상세 정보가 즉시 표시됩니다.")
