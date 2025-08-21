# --- 0. 필요한 라이브러리 가져오기 ---
import streamlit as st
import pandas as pd
import folium
import re
from streamlit_folium import st_folium
import os
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import urllib.parse
import json
import time

# --- 1. 페이지 기본 설정 ---
st.set_page_config(page_title="유선 가평재난 대응 대시보드", page_icon="🗺️", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="st-"], [class*="css-"] {
        font-size: 10px; /* 이 값을 조절하여 폰트 크기를 변경할 수 있습니다. */
    }
    </style>
    """,
            unsafe_allow_html=True)


# --- 2-1. 광케이블 데이터 로딩 함수 ---
@st.cache_data
def load_cable_data(filename):
    if not os.path.exists(filename): return None
    try:
        df = pd.read_excel(filename)
    except Exception as e:
        st.error(f"'{filename}' 읽기 오류: {e}")
        return None

    def parse_linestring_for_apply(text):
        if not isinstance(text, str): return None
        try:
            coords_str = re.findall(r'(\d+\.\d+\s\d+\.\d+)', text)
            if not coords_str: return None
            return [[float(p.split()[1]),
                     float(p.split()[0])] for p in coords_str]
        except (ValueError, IndexError):
            return None

    if '공간위치G' not in df.columns: return None
    df['parsed_coords'] = df['공간위치G'].apply(parse_linestring_for_apply)
    return df.dropna(subset=['parsed_coords']).copy()


# --- 2-2. 복구 상태 데이터 로딩 함수 ---
@st.cache_data
def load_recovery_status_data(filename):
    if not os.path.exists(filename): return None
    try:
        df = pd.read_excel(filename)
    except Exception as e:
        st.error(f"'{filename}' 읽기 오류: {e}")
        return None

    def geocode_address(address, geolocator):
        if not isinstance(address, str) or not address.strip():
            return None
        try:
            location = geolocator(address)
            if location:
                return (location.latitude, location.longitude)
            return None
        except Exception as e:
            return None

    geolocator_instance = Nominatim(user_agent="gapyeong_dashboard_app_v3",
                                    timeout=10)
    geocode_with_delay = RateLimiter(geolocator_instance.geocode,
                                     min_delay_seconds=1)

    ADDRESS_COLUMN = '주소'
    if ADDRESS_COLUMN in df.columns:
        df[['geocoded_lat', 'geocoded_lon']] = df[ADDRESS_COLUMN].apply(
            lambda addr: pd.Series(geocode_address(addr, geocode_with_delay)))
    else:
        df['geocoded_lat'] = None
        df['geocoded_lon'] = None

    def parse_dms_to_dd(dms_str):
        if not isinstance(dms_str, str): return None
        try:
            parts = re.match(r'([NSEW])\s*(\d+):(\d+):([\d\.]+)',
                             dms_str.strip())
            if not parts: return None
            direction, degrees, minutes, seconds = parts.groups()
            degrees, minutes, seconds = float(degrees), float(minutes), float(
                seconds)
            dd = degrees + (minutes / 60.0) + (seconds / 3600.0)
            if direction in ('S', 'W'): dd *= -1
            return dd
        except (ValueError, TypeError):
            return None

    LAT_DATA_COLUMN = '경도'
    LON_DATA_COLUMN = '위도'

    if LAT_DATA_COLUMN in df.columns and LON_DATA_COLUMN in df.columns:
        df['latitude_dd'] = df[LAT_DATA_COLUMN].apply(parse_dms_to_dd)
        df['longitude_dd'] = df[LON_DATA_COLUMN].apply(parse_dms_to_dd)
    else:
        df['latitude_dd'] = None
        df['longitude_dd'] = None

    df_valid = df[(df['geocoded_lat'].notna() & df['geocoded_lon'].notna()) |
                  (df['latitude_dd'].notna()
                   & df['longitude_dd'].notna())].copy()

    return df_valid


# --- 2-3. 진행 현황 데이터 로딩 함수 ---
@st.cache_data
def load_progress_data(filename):
    if not os.path.exists(filename):
        st.warning(f"'{filename}' 파일을 찾을 수 없어 해당 기능을 비활성화합니다.")
        return None
    try:
        df = pd.read_excel(filename, sheet_name=0)
        return df
    except Exception as e:
        st.error(f"'{filename}' 파일 읽기 오류: {e}")
        return None


# --- 2-4. 중계기 현황 데이터 로딩 함수 ---
@st.cache_data
def load_repeater_recovery_data(filename):
    if not os.path.exists(filename):
        st.warning(f"'{filename}' 파일을 찾을 수 없어 '복구예정 중계기' 테이블을 표시할 수 없습니다.")
        return None
    try:
        df = pd.read_excel(filename, sheet_name='Sheet2')
        return df
    except Exception as e:
        st.error(
            f"'{filename}' 파일에서 'Sheet2' 시트를 읽는 중 오류가 발생했습니다. 시트 이름이 정확한지 확인해주세요. (오류: {e})"
        )
        return None


# --- 3. 메인 대시보드 함수 ---
def show_dashboard():
    st.title("🗺️ 유선 가평재난 대응 대시보드")

    geojson_data = {
        "type":
        "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {
                "coordinates": [[[127.2806953180476, 37.78729788838481],
                                 [127.2765499549609, 37.7771712447948],
                                 [127.29576936563382, 37.774788303497445],
                                 [127.34852853218655, 37.79280739100005],
                                 [127.37641552022086, 37.7916161819997],
                                 [127.3538044488406, 37.812906146199694],
                                 [127.3129160947625, 37.81007776322896],
                                 [127.28917446981495, 37.804867300456266],
                                 [127.2806953180476, 37.78729788838481]]],
                "type":
                "Polygon"
            }
        }, {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "coordinates": [[[127.30114246707063, 37.83937277697714],
                                 [127.30281667537503, 37.826645709902834],
                                 [127.32939473223814, 37.81705763830212],
                                 [127.34174201849481, 37.82350492707792],
                                 [127.34153274245756, 37.83986859229668],
                                 [127.32855762808498, 37.85110617888827],
                                 [127.30825785237084, 37.8494537000242],
                                 [127.30114246707063, 37.83937277697714]]],
                "type":
                "Polygon"
            }
        }, {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "coordinates": [[[127.35785627344296, 37.840860212937045],
                                 [127.3553449609833, 37.83176985807101],
                                 [127.3685293513953, 37.828959885397154],
                                 [127.40285062167248, 37.84119075018792],
                                 [127.41122166320247, 37.85837664589687],
                                 [127.4055712101694, 37.8720894383471],
                                 [127.36978500762501, 37.870272226993634],
                                 [127.35283364852381, 37.8514366702168],
                                 [127.35785627344296, 37.840860212937045]]],
                "type":
                "Polygon"
            }
        }, {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "coordinates": [[[127.38208718030882, 37.789871082070206],
                                 [127.38456298052728, 37.77337845393433],
                                 [127.3948198671464, 37.75939876981431],
                                 [127.41674838336314, 37.76694812744792],
                                 [127.41922418358149, 37.79406353636617],
                                 [127.3891608952186, 37.82312467645714],
                                 [127.36369552154696, 37.81362517748403],
                                 [127.38208718030882, 37.789871082070206]]],
                "type":
                "Polygon"
            }
        }, {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "coordinates": [[[127.51803924542475, 37.83135101098242],
                                 [127.51825739118652, 37.842377117042346],
                                 [127.51324003864227, 37.8523681020244],
                                 [127.49622466914303, 37.868385304016414],
                                 [127.4678657199762, 37.87837276434155],
                                 [127.45630399454893, 37.86804088468334],
                                 [127.44365154030442, 37.8523681020244],
                                 [127.44801445556118, 37.83307394869125],
                                 [127.48095446574649, 37.81963396756811],
                                 [127.51803924542475, 37.83135101098242]]],
                "type":
                "Polygon"
            }
        }]
    }

    st.sidebar.title("⚙️ 앱 관리")
    if st.sidebar.button("🔄 데이터 새로고침", help="엑셀 파일 변경 사항을 앱에 반영합니다."):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.markdown("---")

    # [수정] 세션 상태 초기화를 위해 데이터 로딩을 먼저 수행
    df_cable = load_cable_data("광케이블가평.xlsx")
    df_recovery = load_recovery_status_data("복구미복구국소.xlsx")
    df_progress = load_progress_data("진행현황.xlsx")
    df_repeater = load_repeater_recovery_data("진행현황.xlsx")

    # [수정] 점검 내역 전체 목록을 미리 준비
    inspection_options = []
    if df_recovery is not None:
        INSPECTION_COL = '점검내역(정전/선로불량/유니트)'
        if INSPECTION_COL in df_recovery.columns:
            inspection_options = sorted([
                str(item)
                for item in df_recovery[INSPECTION_COL].dropna().unique()
            ])

    # [수정] 세션 상태 초기화
    if 'show_cable_by_emd' not in st.session_state:
        st.session_state.show_cable_by_emd = False
    if 'view_all_cables' not in st.session_state:
        st.session_state.view_all_cables = False
    if 'selected_emds' not in st.session_state:
        st.session_state.selected_emds = []
    if 'recovery_status_filter' not in st.session_state:
        st.session_state.recovery_status_filter = ['미복구']
    if 'inspection_filter' not in st.session_state:
        # 점검 내역 필터의 기본값을 전체 목록으로 설정
        st.session_state.inspection_filter = inspection_options
    if 'show_clusters' not in st.session_state:
        st.session_state.show_clusters = False

    # 테이블 정보 표시
    with st.expander("📜 진행 현황 상세 정보 보기", expanded=False):
        if df_progress is not None:
            st.dataframe(df_progress, use_container_width=True)
        else:
            st.info("진행 현황 데이터가 없습니다.")

    with st.expander("📋 복구예정 중계기 및 복구현황 보기", expanded=False):
        if df_repeater is not None:
            st.dataframe(df_repeater, use_container_width=True)
        else:
            st.info("'진행현황.xlsx' 파일의 'Sheet2'를 찾을 수 없거나 데이터가 없습니다.")

    st.markdown("---")

    # 사이드바 UI
    st.sidebar.header("🗺️ 광케이블 선택")
    if st.sidebar.button("전체 보기"):
        st.session_state.update(view_all_cables=True,
                                show_cable_by_emd=False,
                                selected_emds=[])
        st.rerun()
    if st.sidebar.button("읍면동별 보기/숨기기"):
        st.session_state.update(
            show_cable_by_emd=not st.session_state.show_cable_by_emd,
            view_all_cables=False)
        st.rerun()
    if st.session_state.show_cable_by_emd and df_cable is not None:
        EUP_MYEON_DONG_COLUMN = '읍면동명'
        if EUP_MYEON_DONG_COLUMN in df_cable.columns:
            emd_list = sorted(
                df_cable[EUP_MYEON_DONG_COLUMN].dropna().unique())
            st.session_state.selected_emds = st.sidebar.multiselect(
                "읍면동 선택",
                options=emd_list,
                default=st.session_state.selected_emds,
                on_change=lambda: st.session_state.update(view_all_cables=False
                                                          ))

    st.sidebar.markdown("---")
    st.sidebar.header("📍 국소 상태 필터")
    if df_recovery is not None:
        RECOVERY_STATUS_COL = '복구상태'
        INSPECTION_COL = '점검내역(정전/선로불량/유니트)'
        if RECOVERY_STATUS_COL in df_recovery.columns:
            status_options = list(
                df_recovery[RECOVERY_STATUS_COL].dropna().unique())
            valid_defaults = [
                d for d in st.session_state.recovery_status_filter
                if d in status_options
            ]
            st.session_state.recovery_status_filter = st.sidebar.multiselect(
                "복구/미복구 보기", options=status_options, default=valid_defaults)

        # inspection_options는 위에서 이미 준비됨
        if inspection_options:
            valid_defaults = [
                d for d in st.session_state.inspection_filter
                if d in inspection_options
            ]
            st.session_state.inspection_filter = st.sidebar.multiselect(
                "점검 내역 보기", options=inspection_options, default=valid_defaults)
            if st.sidebar.button("점검 내역 전체 보기"):
                st.session_state.inspection_filter = inspection_options
                st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("🗺️ 지도 레이어")
    if st.sidebar.button("클러스터 보기/숨기기"):
        st.session_state.show_clusters = not st.session_state.show_clusters
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("↔️ 지도 크기 조절")
    map_height = st.sidebar.slider("지도 높이를 선택하세요 (px)",
                                   min_value=300,
                                   max_value=1200,
                                   value=500,
                                   step=50)

    st.sidebar.markdown("---")
    st.sidebar.header("📜 범례 (Legend)")
    legend_html_sidebar = """
    <style>
        .legend-item { display: flex; align-items: center; margin-bottom: 8px; font-size: 14px; }
        .legend-color { width: 15px; height: 15px; margin-right: 10px; border: 1px solid #ddd;}
        .legend-line { width: 20px; height: 3px; margin-right: 10px; }
        .legend-icon { font-size: 20px; margin-right: 10px; }
        .pulsing-dot { border-radius: 50%; animation: pulse 1.5s infinite; }
        @keyframes pulse {
            0% { transform: scale(0.8); box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.7); }
            70% { transform: scale(1.2); box-shadow: 0 0 10px 10px rgba(0, 0, 0, 0); }
            100% { transform: scale(0.8); box-shadow: 0 0 0 0 rgba(0, 0, 0, 0); }
        }
    </style>
    <div class="legend-item"><div class="legend-color" style="background-color:rgba(255, 255, 0, 0.4); border-radius: 5px;"></div><span>클러스터</span></div>
    <div class="legend-item"><div class="legend-line" style="background-color:red;"></div><span>광케이블</span></div>
    <div class="legend-item"><div class="legend-color" style="background-color:blue; border-radius: 50%;"></div><span>국소 (복구)</span></div>
    <div class="legend-item"><div class="legend-color" style="background-color:red; border: 2px solid yellow; border-radius: 50%;"></div><span>국소 (미복구)</span></div>
    <hr style="margin: 8px 0;">
    <div class="legend-item"><span class="legend-icon">📡</span><span>이동기지국</span></div>
    <div class="legend-item"><div class="legend-color pulsing-dot" style="background-color:#9370DB;"></div><span>작업완료</span></div>
    <div class="legend-item"><div class="legend-color pulsing-dot" style="background-color:#007bff;"></div><span>진행중</span></div>
    <div class="legend-item"><div class="legend-color pulsing-dot" style="background-color:#28a745;"></div><span>현장확인</span></div>
    <div class="legend-item"><div class="legend-color" style="background-color:gray; border-radius: 50%;"></div><span>기타 상태</span></div>
    """
    st.sidebar.markdown(legend_html_sidebar, unsafe_allow_html=True)

    # 지도 생성
    map_center = [37.8313, 127.5095]
    m = folium.Map(location=map_center, zoom_start=11)
    folium.TileLayer('CartoDB positron', name='일반 지도').add_to(m)
    folium.TileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='위성 지도').add_to(m)

    if st.session_state.show_clusters:
        style_function = lambda x: {
            'fillColor': 'yellow',
            'color': 'orange',
            'weight': 2,
            'fillOpacity': 0.3
        }
        folium.GeoJson(geojson_data,
                       name='클러스터 영역',
                       style_function=style_function).add_to(m)

    if st.session_state.view_all_cables and df_cable is not None:
        for _, row in df_cable.iterrows():
            folium.PolyLine(locations=row['parsed_coords'],
                            color='red',
                            weight=2.5,
                            tooltip='광케이블').add_to(m)
    elif st.session_state.selected_emds and df_cable is not None:
        filtered_df_cable = df_cable[df_cable['읍면동명'].isin(
            st.session_state.selected_emds)]
        for _, row in filtered_df_cable.iterrows():
            folium.PolyLine(locations=row['parsed_coords'],
                            color='red',
                            weight=2.5,
                            tooltip=row.get('읍면동명', '광케이블')).add_to(m)

    if df_recovery is not None:
        filtered_df_recovery = df_recovery[df_recovery['복구상태'].isin(
            st.session_state.recovery_status_filter)]
        if st.session_state.inspection_filter and '점검내역(정전/선로불량/유니트)' in filtered_df_recovery.columns:
            filtered_df_recovery = filtered_df_recovery[
                filtered_df_recovery['점검내역(정전/선로불량/유니트)'].astype(str).isin(
                    st.session_state.inspection_filter)]

        color_map = {'복구': 'blue', '미복구': 'red'}
        for _, row in filtered_df_recovery.iterrows():
            lat = row['geocoded_lat'] if pd.notna(
                row['geocoded_lat']) else row['latitude_dd']
            lon = row['geocoded_lon'] if pd.notna(
                row['geocoded_lon']) else row['longitude_dd']

            if pd.notna(lat) and pd.notna(lon):
                status = row.get('복구상태', '정보 없음')
                coord_source = "주소기반" if pd.notna(
                    row['geocoded_lat']) else "엑셀좌표(DMS)"
                popup_info = [
                    f"<b>국소명:</b> {row.get('국소명', '정보 없음')}",
                    f"<b>주소:</b> {row.get('주소', '정보 없음')}",
                    f"<b>복구 상태:</b> {status}",
                    f"<b>장비 종류:</b> {row.get('RU / 중계기=>중계기 종류', '정보 없음')}",
                    f"<b>공동망 구분:</b> {row.get('공동망구분', '정보 없음')}",
                    f"<b>점검 내역:</b> {row.get('점검내역(정전/선로불량/유니트)', '정보 없음')}",
                    f"<b>위치정보 소스:</b> {coord_source}"
                ]
                popup_html = "<br>".join(popup_info)
                border_color = 'yellow' if status == '미복구' else 'white'

                folium.CircleMarker(location=[lat, lon],
                                    radius=7,
                                    color=border_color,
                                    weight=2,
                                    fill=True,
                                    fill_color=color_map.get(status, 'gray'),
                                    fill_opacity=1.0,
                                    popup=folium.Popup(
                                        popup_html, max_width=300)).add_to(m)

    if df_progress is not None:
        df_progress_map = df_progress.copy()

        def parse_latlon_string(text):
            if not isinstance(text, str): return None
            try:
                lat, lon = map(float, text.split(','))
                return [lat, lon]
            except (ValueError, IndexError):
                return None

        COORD_COL = '위경도'
        if COORD_COL in df_progress_map.columns:
            df_progress_map['parsed_coords'] = df_progress_map[
                COORD_COL].apply(parse_latlon_string)
            df_progress_map.dropna(subset=['parsed_coords'], inplace=True)

            for _, row in df_progress_map.iterrows():
                popup_info = [
                    f"<b>{k}:</b> {v}" for k, v in row.items()
                    if k not in ['parsed_coords', '위경도']
                ]
                popup_html = "<br>".join(popup_info)
                division = str(row.get('구분', ""))
                status = row.get('진행여부')
                icon = None
                if '이동기지국' in division:
                    icon = folium.DivIcon(
                        html='<div style="font-size: 24px;">📡</div>',
                        icon_size=(30, 30),
                        icon_anchor=(15, 15))
                else:
                    pulsing_icon_colors = {
                        '현장확인': '#28a745',
                        '작업완료': '#9370DB',
                        '진행중': '#007bff'
                    }
                    color = pulsing_icon_colors.get(status)
                    if color:
                        pulsing_icon_html = f"""<div style="width:24px;height:24px;border-radius:50%;background-color:{color};border:2px solid white;box-shadow:0 0 8px {color};animation:pulse_{status} 1.5s infinite;position:relative;top:-12px;left:-12px;"></div><style>@keyframes pulse_{status}{{0%{{transform:scale(0.8);box-shadow:0 0 0 0 {color}aa}}70%{{transform:scale(1.2);box-shadow:0 0 10px 10px {color}00}}100%{{transform:scale(0.8);box-shadow:0 0 0 0 {color}00}}}}</style>"""
                        icon = folium.DivIcon(html=pulsing_icon_html,
                                              icon_size=(24, 24),
                                              icon_anchor=(12, 12))
                    else:
                        icon = folium.Icon(color='gray', icon='info-sign')
                folium.Marker(location=row['parsed_coords'],
                              popup=folium.Popup(popup_html, max_width=400),
                              icon=icon).add_to(m)

    folium.LayerControl().add_to(m)
    map_data = st_folium(m,
                         width='100%',
                         height=map_height,
                         returned_objects=['last_clicked'])

    with st.expander("📊 가평 전체 국소 현황 보기", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        total_count, recovered_count, unrecovered_count, recovery_rate = 0, 0, 0, 0.0
        if df_recovery is not None:
            RECOVERY_STATUS_COL = '복구상태'
            total_count = len(df_recovery)
            if RECOVERY_STATUS_COL in df_recovery.columns and total_count > 0:
                recovered_count = len(
                    df_recovery[df_recovery[RECOVERY_STATUS_COL] == '복구'])
                unrecovered_count = len(
                    df_recovery[df_recovery[RECOVERY_STATUS_COL] == '미복구'])
                recovery_rate = (recovered_count /
                                 total_count) * 100 if total_count > 0 else 0
        col1.metric(label="총 국소", value=total_count)
        col2.metric(label="복구", value=recovered_count)
        col3.metric(label="미복구", value=unrecovered_count)
        col4.metric(label="복구율 (%)", value=f"{recovery_rate:.1f} %")

    with st.expander("📊 유선 RM 복구 현황 보기", expanded=False):
        col5, col6, col7, col8 = st.columns(4)
        rm_total, rm_recovered, rm_unrecovered, rm_recovery_rate = 0, 0, 0, 0.0
        if df_recovery is not None:
            RECOVERY_STATUS_COL = '복구상태'
            INSPECTION_COL = '점검내역(정전/선로불량/유니트)'
            if INSPECTION_COL in df_recovery.columns:
                target_inspections = ['선로불량', '정전/선로불량']
                # isin()은 문자열 비교를 기본으로 하므로 .astype(str)로 안전하게 변환
                df_rm_special = df_recovery[df_recovery[INSPECTION_COL].astype(
                    str).isin(target_inspections)]
                rm_total = len(df_rm_special)
                if rm_total > 0:
                    rm_recovered = len(df_rm_special[
                        df_rm_special[RECOVERY_STATUS_COL] == '복구'])
                    rm_unrecovered = len(df_rm_special[
                        df_rm_special[RECOVERY_STATUS_COL] == '미복구'])
                    rm_recovery_rate = (rm_recovered /
                                        rm_total) * 100 if rm_total > 0 else 0
        col5.metric(label="총 대상", value=rm_total)
        col6.metric(label="복구", value=rm_recovered)
        col7.metric(label="미복구", value=rm_unrecovered)
        col8.metric(label="복구율 (%)", value=f"{rm_recovery_rate:.1f} %")

    with st.expander("🌐 선택 위치 주소 보기", expanded=False):
        if map_data and map_data.get("last_clicked"):
            lat, lng = map_data["last_clicked"]["lat"], map_data[
                "last_clicked"]["lng"]
            geolocator = Nominatim(user_agent="gapyeong_dashboard_app")
            try:
                location = geolocator.reverse((lat, lng), language="ko")
                address = location.address if location else "주소를 찾을 수 없습니다."
                st.success(f"선택한 위치의 주소: {address}")
            except Exception as e:
                st.error(f"주소 변환 중 오류가 발생했습니다: {e}")
        else:
            st.info("지도 위를 클릭하면 해당 위치의 주소가 표시됩니다. 마커를 클릭하면 상세 정보가 나타납니다.")


if __name__ == "__main__":
    show_dashboard()
