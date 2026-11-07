from unittest.mock import patch

import pytest

from src.tools.amap.route import RouteResolutionError, RouteTool


class TestRouteTool:
    """路线工具单元测试。"""

    def test_get_driving_route_success(self, mock_http):
        """测试成功获取驾车路线。"""
        mock_http(
            {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "duration": "1800",
                            "distance": "5000",
                            "steps": [{"instruction": "沿长安街向东行驶"}],
                        }
                    ]
                },
            }
        )
        # 传入坐标避免触发地理编码分支
        result = RouteTool.get_driving_route("116.39,39.90", "116.40,39.91")
        assert result is not None
        assert "route" in result

    def test_get_driving_route_failure(self, mock_http):
        """测试获取驾车路线失败：高德 status!="1" 时返回 None（不再透传错误体）。"""
        mock_http({"status": "0", "info": "错误"})
        result = RouteTool.get_driving_route("116.39,39.90", "116.40,39.91")
        assert result is None

    def test_get_transit_route_success(self, mock_http):
        """测试成功获取公交路线。"""
        mock_http(
            {
                "status": "1",
                "route": {
                    "transits": [
                        {
                            "duration": "3600",
                            "walking_distance": "500",
                            "segments": [{"bus": {"buslines": [{"name": "1路公交车"}]}}],
                        }
                    ]
                },
            }
        )
        result = RouteTool.get_transit_route("116.39,39.90", "116.40,39.91", "北京")
        assert result is not None
        assert "route" in result

    def test_get_transit_route_failure(self, mock_http):
        """测试获取公交路线失败：高德 status!="1" 时返回 None（不再透传错误体）。"""
        mock_http({"status": "0", "info": "错误"})
        result = RouteTool.get_transit_route("116.39,39.90", "116.40,39.91", "北京")
        assert result is None

    def test_format_driving_route_success(self):
        """测试格式化驾车路线。"""
        route_data = {
            "route": {
                "paths": [
                    {
                        "duration": "1800",
                        "distance": "5000",
                        "steps": [
                            {"instruction": "沿长安街向东行驶"},
                            {"instruction": "到达目的地"},
                        ],
                    }
                ]
            }
        }
        result = RouteTool.format_driving_route(route_data)
        assert "驾车路线规划" in result
        assert "30分钟" in result
        assert "5.0公里" in result
        assert "沿长安街向东行驶" in result

    def test_format_driving_route_empty(self):
        """测试格式化空驾车路线。"""
        result = RouteTool.format_driving_route({})
        assert result == "暂无路线信息"

    def test_format_transit_route_unit_conversion(self):
        """测试公交路线的秒->分钟、米->公里单位转换（核心修复点）。"""
        route_data = {
            "route": {
                "transits": [
                    {
                        "duration": "3600",  # 3600 秒 = 60 分钟
                        "walking_distance": "500",  # 500 米 = 0.5 公里
                        "segments": [
                            {
                                "bus": {
                                    "buslines": [
                                        {"name": "1路公交车"},
                                        {"name": "地铁1号线"},
                                    ]
                                }
                            }
                        ],
                    }
                ]
            }
        }
        result = RouteTool.format_transit_route(route_data)
        assert "公交路线规划" in result
        assert "方案1" in result
        assert "1路公交车" in result
        assert "地铁1号线" in result
        # 关键断言：单位已正确转换，不再出现原始秒数 / 米数。
        # 3600 秒 = 60 分钟 -> >=60 分钟按"小时"格式输出为"1小时0分钟"
        assert "1小时0分钟" in result
        assert "0.5公里" in result
        assert "3600秒" not in result
        assert "500米" not in result

    def test_format_transit_route_empty(self):
        """测试格式化空公交路线。"""
        result = RouteTool.format_transit_route({})
        assert result == "暂无公交路线信息"

    def test_plan_multi_spot_route_success(self, mock_http):
        """测试规划多景点路线（地名先经地理编码再规划）。"""
        # 让地理编码返回固定坐标
        with patch("src.tools.amap.geocode.geocode") as mock_geo:
            mock_geo.side_effect = ["116.39,39.90", "116.40,39.91", "116.27,39.99"]
            # 让路线接口返回固定路径
            mock_http(
                {
                    "status": "1",
                    "route": {
                        "paths": [{"duration": "1800", "distance": "5000", "steps": []}]
                    },
                }
            )
            result = RouteTool.plan_multi_spot_route(["天安门", "故宫", "颐和园"], city="北京")
            assert result is not None
            assert "segments" in result
            assert len(result["segments"]) == 2
            assert result["total_duration"] > 0

    def test_plan_multi_spot_route_geocode_failed(self, mock_http):
        """测试多景点路线中存在无法定位的地名时给出明确错误（核心修复点）。"""
        with patch("src.tools.amap.geocode.geocode") as mock_geo:
            mock_geo.return_value = None  # 地理编码全部失败
            result = RouteTool.plan_multi_spot_route(
                ["某不存在的地方甲", "某不存在的地方乙"], city="火星"
            )
            assert "error" in result
            assert "无法定位" in result["error"]

    def test_plan_multi_spot_route_single_spot(self):
        """测试单个景点规划路线。"""
        result = RouteTool.plan_multi_spot_route(["天安门"], city="北京")
        assert "error" in result

    def test_format_multi_spot_route_success(self):
        """测试格式化多景点路线。"""
        plan_data = {
            "segments": [
                {
                    "from": "天安门",
                    "to": "故宫",
                    "duration_minutes": 30,
                    "distance_km": 5.0,
                },
                {
                    "from": "故宫",
                    "to": "颐和园",
                    "duration_minutes": 60,
                    "distance_km": 15.0,
                },
            ],
            "total_duration": 90,
            "total_distance": 20.0,
            "spot_count": 3,
            "mode": "driving",
        }
        result = RouteTool.format_multi_spot_route(plan_data)
        assert "多景点路线规划" in result
        assert "天安门" in result
        assert "故宫" in result
        assert "颐和园" in result
        assert "90 分钟" in result
        assert "20.0 公里" in result

    def test_strip_tags_removes_html(self):
        """HTML 标签应被完整剥离，而非仅去掉尖括号。"""
        from src.tools.amap.route import _strip_tags

        assert _strip_tags("<b>左转</b>") == "左转"
        assert _strip_tags("直行<span>200</span>米") == "直行200米"

    def test_format_driving_route_strips_tags(self):
        """驾车路线步骤中的 HTML 标签应被剥离（核心修复点）。"""
        route_data = {
            "route": {
                "paths": [
                    {
                        "duration": "600",
                        "distance": "1000",
                        "steps": [{"instruction": "<b>左转</b>进入长安街"}],
                    }
                ]
            }
        }
        result = RouteTool.format_driving_route(route_data)
        assert "左转进入长安街" in result
        assert "b左转" not in result

    def test_get_walking_route_success(self, mock_http):
        """测试步行路线获取。"""
        mock_http(
            {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "duration": "900",
                            "distance": "800",
                            "steps": [{"instruction": "直行", "distance": "400"}],
                        }
                    ]
                },
            }
        )
        result = RouteTool.get_walking_route("116.39,39.90", "116.40,39.91")
        assert result is not None
        assert "route" in result

    def test_format_walking_route_success(self):
        """测试步行路线格式化。"""
        route_data = {
            "route": {
                "paths": [
                    {
                        "duration": "900",
                        "distance": "800",
                        "steps": [{"instruction": "<b>直行</b>", "distance": "400"}],
                    }
                ]
            }
        }
        result = RouteTool.format_walking_route(route_data)
        assert "步行路线规划" in result
        assert "0.8公里" in result
        assert "直行" in result
        assert "b直行" not in result

    def test_plan_multi_spot_transit_requires_city(self):
        """公交模式未提供城市时应返回明确错误（核心修复点）。"""
        result = RouteTool.plan_multi_spot_route(["天安门", "故宫"], city="", mode="transit")
        assert "error" in result
        assert "城市" in result["error"]

    def test_safe_int_and_float(self):
        """数值转换容错：非法值返回 0。"""
        from src.tools.amap.route import _safe_float, _safe_int

        assert _safe_int("1800") == 1800
        assert _safe_int("abc") == 0
        assert _safe_int(None) == 0
        assert _safe_float("5.5") == 5.5
        assert _safe_float("x") == 0.0

    def test_unresolvable_origin_raises(self, mock_http):
        """地理编码失败时应抛 RouteResolutionError（不再静默把地名传给路线接口）。"""
        mock_http({"status": "0", "info": "INVALID_PARAMS"})
        with pytest.raises(RouteResolutionError) as exc:
            RouteTool.get_driving_route("不存在的地方", "故宫")
        assert "无法定位起点" in str(exc.value)

    def test_unresolvable_destination_raises(self, mock_http):
        mock_http({"status": "0", "info": "INVALID_PARAMS"})
        with pytest.raises(RouteResolutionError) as exc:
            # 起点传坐标（跳过地理编码），终点传无法定位的地名
            RouteTool.get_driving_route("116.39,39.90", "不存在的地方")
        assert "无法定位终点" in str(exc.value)

    def test_coord_input_skips_geocode(self, mock_http):
        """已是坐标的输入不触发地理编码。"""
        with patch("src.tools.amap.route.geocode.geocode_or_raw") as m_geo:
            mock_http({"status": "1", "route": {"paths": []}})
            RouteTool.get_driving_route("116.39,39.90", "116.40,39.91")
            m_geo.assert_not_called()


class TestProximityOrdering:
    """多景点就近贪心排序（optimize_order）。"""

    def test_greedy_nearest_neighbor(self):
        from src.tools.amap.route import order_spots_by_proximity

        # A(0,0) B(0,0.1) C(0,10)：输入 A C B 应优化为 A B C
        spots = ["A", "C", "B"]
        coords = ["116.0,0.0", "116.0,10.0", "116.0,0.1"]
        new_spots, new_coords = order_spots_by_proximity(spots, coords)
        assert new_spots == ["A", "B", "C"]
        assert new_coords == ["116.0,0.0", "116.0,0.1", "116.0,10.0"]

    def test_single_spot_noop(self):
        from src.tools.amap.route import order_spots_by_proximity

        assert order_spots_by_proximity(["A"], ["116.0,0.0"]) == (["A"], ["116.0,0.0"])

    def test_unparseable_coord_keeps_tail(self):
        from src.tools.amap.route import order_spots_by_proximity

        spots = ["A", "B", "C"]
        coords = ["116.0,0.0", "bad-coord", "116.0,0.1"]
        new_spots, new_coords = order_spots_by_proximity(spots, coords)
        # B 无法解析，按原相对顺序排在可解析项之后
        assert new_spots[0] == "A"
        assert set(new_spots) == {"A", "B", "C"}
        assert len(new_coords) == 3

    def test_plan_multi_spot_optimize_order(self, mock_http):
        """optimize_order=True 时先重排再规划。"""
        with patch("src.tools.amap.route.geocode.geocode_many") as m_geo, patch(
            "src.tools.amap.route.RouteTool.get_driving_route"
        ) as m_route:
            m_geo.return_value = (["116.0,0.0", "116.0,10.0", "116.0,0.1"], [])
            m_route.return_value = {
                "route": {"paths": [{"duration": "600", "distance": "1000"}]}
            }
            result = RouteTool.plan_multi_spot_route(
                ["A", "C", "B"], city="北京", optimize_order=True
            )
            assert result["optimized"] is True
            # 第一段应为 A -> B（就近），而不是 A -> C
            assert result["segments"][0]["from"] == "A"
            assert result["segments"][0]["to"] == "B"

    def test_plan_multi_spot_no_optimize_flag(self, mock_http):
        with patch("src.tools.amap.route.geocode.geocode_many") as m_geo, patch(
            "src.tools.amap.route.RouteTool.get_driving_route"
        ) as m_route:
            m_geo.return_value = (["116.0,0.0", "116.0,0.1"], [])
            m_route.return_value = {
                "route": {"paths": [{"duration": "600", "distance": "1000"}]}
            }
            result = RouteTool.plan_multi_spot_route(["A", "B"], city="北京")
            assert result["optimized"] is False
