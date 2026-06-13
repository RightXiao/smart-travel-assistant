import pytest
from unittest.mock import Mock, patch
from src.tools.amap.route import RouteTool


class TestRouteTool:
    """路线工具单元测试。"""

    @patch("src.tools.amap.route.requests.get")
    def test_get_driving_route_success(self, mock_get):
        """测试成功获取驾车路线。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "route": {
                "paths": [
                    {
                        "duration": "1800",
                        "distance": "5000",
                        "steps": [
                            {
                                "instruction": "沿长安街向东行驶",
                            }
                        ],
                    }
                ]
            },
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RouteTool.get_driving_route("天安门", "故宫")
        assert result is not None
        assert "route" in result

    @patch("src.tools.amap.route.requests.get")
    def test_get_driving_route_failure(self, mock_get):
        """测试获取驾车路线失败。"""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "0", "info": "错误"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RouteTool.get_driving_route("天安门", "故宫")
        assert result is None

    @patch("src.tools.amap.route.requests.get")
    def test_get_transit_route_success(self, mock_get):
        """测试成功获取公交路线。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "route": {
                "transits": [
                    {
                        "duration": "3600",
                        "walking_distance": "500",
                        "segments": [
                            {
                                "bus": {
                                    "buslines": [
                                        {"name": "1路公交车"}
                                    ]
                                }
                            }
                        ],
                    }
                ]
            },
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RouteTool.get_transit_route("天安门", "故宫", "北京")
        assert result is not None
        assert "route" in result

    @patch("src.tools.amap.route.requests.get")
    def test_get_transit_route_failure(self, mock_get):
        """测试获取公交路线失败。"""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "0", "info": "错误"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = RouteTool.get_transit_route("天安门", "故宫", "北京")
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

    def test_format_transit_route_success(self):
        """测试格式化公交路线。"""
        route_data = {
            "route": {
                "transits": [
                    {
                        "duration": "3600",
                        "walking_distance": "500",
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

    def test_format_transit_route_empty(self):
        """测试格式化空公交路线。"""
        result = RouteTool.format_transit_route({})
        assert result == "暂无公交路线信息"

    def test_plan_multi_spot_route_success(self):
        """测试规划多景点路线。"""
        # 由于 plan_multi_spot_route 会调用 get_driving_route，需要 mock
        with patch.object(RouteTool, "get_driving_route") as mock_get:
            mock_get.return_value = {
                "route": {
                    "paths": [
                        {
                            "duration": "1800",
                            "distance": "5000",
                            "steps": [],
                        }
                    ]
                }
            }
            result = RouteTool.plan_multi_spot_route(
                ["天安门", "故宫", "颐和园"], city="北京"
            )
            assert result is not None
            assert "segments" in result
            assert len(result["segments"]) == 2
            assert result["total_duration"] > 0

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
