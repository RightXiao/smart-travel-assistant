import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.agents.travel_assistant import TravelAssistant

st.set_page_config(
    page_title="智能旅行助手",
    page_icon="🧳",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_assistant():
    try:
        return TravelAssistant()
    except Exception as e:
        st.error(f"初始化助手失败：{e}")
        st.info("请确保已在 `.env` 文件中配置了智谱AI和高德地图的 API 密钥。")
        return None


st.title("🧳 智能旅行助手")
st.caption("基于 AI 的智能旅行攻略生成器 — 支持天气查询、景点推荐、路线规划、美食住宿推荐")

# ---------- 侧边栏 ----------
with st.sidebar:
    st.header("📋 使用说明")
    st.markdown("""
    在聊天框中输入你的旅行需求，尽量包含以下信息：
    - 🎯 目的地城市
    - 📅 旅行天数
    - 💰 预算范围
    - 🏛️ 想去的景点类型
    - 🍜 饮食偏好

    **示例：**
    > 我想去北京旅游3天，预算5000元，喜欢历史文化类景点，想吃当地特色小吃
    """)

    st.markdown("---")
    st.header("🛠️ 快捷查询")

    tab1, tab2, tab3 = st.tabs(["🌤️ 天气", "🏛️ 景点", "🍜 美食"])

    with tab1:
        city = st.text_input("城市", placeholder="如：北京", key="weather_city")
        if st.button("查询天气与穿搭", use_container_width=True):
            from src.tools.amap.weather import WeatherTool
            with st.spinner("查询中..."):
                data = WeatherTool.get_weather(city)
                if data:
                    st.success("查询成功")
                    st.markdown(WeatherTool.format_weather_info(data))
                    advice = WeatherTool.get_dressing_advice(data)
                    st.markdown(f"**👗 穿搭建议：**\n{advice}")
                else:
                    st.error("查询失败，请检查 API 配置")

    with tab2:
        spot_city = st.text_input("城市", placeholder="如：上海", key="spot_city")
        if st.button("查询热门景点", use_container_width=True):
            from src.tools.amap.poi import POITool
            with st.spinner("查询中..."):
                data = POITool.search_scenic_spots(spot_city)
                if data:
                    st.success("查询成功")
                    st.markdown(POITool.format_poi_list(data, "热门景点"))
                else:
                    st.error("查询失败")

    with tab3:
        food_city = st.text_input("城市", placeholder="如：成都", key="food_city")
        if st.button("查询当地美食", use_container_width=True):
            from src.tools.amap.poi import POITool
            with st.spinner("查询中..."):
                data = POITool.search_food(food_city)
                if data:
                    st.success("查询成功")
                    st.markdown(POITool.format_poi_list(data, "当地美食"))
                else:
                    st.error("查询失败")

    st.markdown("---")
    st.header("🏨 住宿查询")
    hotel_city = st.text_input("城市", placeholder="如：杭州", key="hotel_city")
    budget = st.selectbox(
        "预算级别",
        ["", "经济型", "舒适型", "高档型", "豪华型"],
        format_func=lambda x: "不限" if x == "" else x,
        key="hotel_budget",
    )
    if st.button("查询住宿", use_container_width=True):
        from src.tools.amap.poi import POITool
        with st.spinner("查询中..."):
            data = POITool.search_hotel_by_budget(hotel_city, budget) if budget else POITool.search_hotel(hotel_city)
            if data:
                st.success("查询成功")
                st.markdown(POITool.format_hotel_with_budget(data, budget))
            else:
                st.error("查询失败")

    st.markdown("---")
    st.header("🚗 路线规划")
    route_origin = st.text_input("起点", placeholder="如：天安门", key="route_origin")
    route_dest = st.text_input("终点", placeholder="如：故宫博物院", key="route_dest")
    route_city = st.text_input("所在城市", placeholder="如：北京", key="route_city")
    route_mode = st.radio("出行方式", ["驾车", "公交"], horizontal=True)
    if st.button("规划路线", use_container_width=True):
        from src.tools.amap.route import RouteTool
        with st.spinner("规划中..."):
            if route_mode == "驾车":
                data = RouteTool.get_driving_route(route_origin, route_dest)
            else:
                data = RouteTool.get_transit_route(route_origin, route_dest, route_city)
            if data:
                st.success("规划成功")
                if route_mode == "驾车":
                    st.markdown(RouteTool.format_driving_route(data))
                else:
                    st.markdown(RouteTool.format_transit_route(data))
            else:
                st.error("路线规划失败")

# ---------- 主聊天区 ----------
assistant = get_assistant()

# 初始化消息历史
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "你好！我是你的智能旅行助手 🌍\n\n"
                "我可以帮你：\n"
                "- 🌤️ 查询实时天气与穿搭建议\n"
                "- 🏛️ 推荐热门景点与路线规划\n"
                "- 🍜 推荐当地特色美食\n"
                "- 🏨 根据预算推荐住宿\n"
                "- 🗺️ 生成完整的旅行攻略\n\n"
                "请告诉我你的旅行计划吧！例如：*\"我想去杭州玩4天，预算3000元，喜欢自然风光\"*"
            ),
        }
    ]

# 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 聊天输入
if prompt := st.chat_input("告诉我你的旅行需求..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🤔 正在为你规划旅行...")

        if assistant:
            chat_history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
            ]
            try:
                response = assistant.chat(prompt, chat_history=chat_history)
                message_placeholder.markdown(response)
            except Exception as e:
                response = f"抱歉，处理请求时出错：{str(e)}"
                message_placeholder.error(response)
        else:
            response = (
                "助手未正确初始化。\n\n"
                "请确保：\n"
                "1. 在项目根目录创建 `.env` 文件\n"
                "2. 配置 `ZHIPUAI_API_KEY` 和 `AMAP_API_KEY`\n"
                "3. 重启应用"
            )
            message_placeholder.warning(response)

    st.session_state.messages.append({"role": "assistant", "content": response})

# 底部：清空对话按钮
st.markdown("---")
col1, col2 = st.columns([1, 1])
with col1:
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
