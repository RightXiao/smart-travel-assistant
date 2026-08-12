from src.tools.amap.weather import WeatherTool


class TestWeatherTool:
    """天气工具单元测试。"""

    def test_get_weather_success(self, mock_http):
        """测试成功获取天气信息。"""
        mock_http(
            {
                "status": "1",
                "lives": [
                    {
                        "city": "北京",
                        "weather": "晴",
                        "temperature": "25",
                        "winddirection": "北",
                        "windpower": "3",
                        "humidity": "45",
                        "reporttime": "2024-01-01 12:00:00",
                    }
                ],
            }
        )
        result = WeatherTool.get_weather("北京")
        assert result is not None
        assert "lives" in result
        assert result["lives"][0]["city"] == "北京"

    def test_get_weather_failure(self, mock_http):
        """测试获取天气信息失败。"""
        mock_http({"status": "0", "info": "错误"})
        result = WeatherTool.get_weather("北京")
        assert result is None

    def test_get_weather_forecast_success(self, mock_http):
        """测试成功获取天气预报。"""
        mock_http(
            {
                "status": "1",
                "forecasts": [
                    {
                        "city": "北京",
                        "casts": [
                            {
                                "date": "2024-01-01",
                                "week": "1",
                                "dayweather": "晴",
                                "nightweather": "多云",
                                "daytemp": "25",
                                "nighttemp": "15",
                                "daywind": "北",
                                "daypower": "3",
                            }
                        ],
                    }
                ],
            }
        )
        result = WeatherTool.get_weather_forecast("北京")
        assert result is not None
        assert "forecasts" in result

    def test_format_weather_info_success(self):
        """测试格式化天气信息。"""
        weather_data = {
            "lives": [
                {
                    "city": "北京",
                    "weather": "晴",
                    "temperature": "25",
                    "winddirection": "北",
                    "windpower": "3",
                    "humidity": "45",
                    "reporttime": "2024-01-01 12:00:00",
                }
            ]
        }
        result = WeatherTool.format_weather_info(weather_data)
        assert "北京" in result
        assert "晴" in result
        assert "25" in result

    def test_format_weather_info_empty(self):
        """测试格式化空天气信息。"""
        result = WeatherTool.format_weather_info({})
        assert result == "暂无天气信息"

    def test_format_forecast_info_success(self):
        """测试格式化天气预报信息。"""
        weather_data = {
            "forecasts": [
                {
                    "city": "北京",
                    "casts": [
                        {
                            "date": "2024-01-01",
                            "week": "1",
                            "dayweather": "晴",
                            "nightweather": "多云",
                            "daytemp": "25",
                            "nighttemp": "15",
                            "daywind": "北",
                            "daypower": "3",
                        }
                    ],
                }
            ]
        }
        result = WeatherTool.format_forecast_info(weather_data)
        assert "北京" in result
        assert "2024-01-01" in result
        assert "周一" in result
        assert "晴" in result

    def test_format_forecast_info_empty(self):
        """测试格式化空预报信息。"""
        assert WeatherTool.format_forecast_info({}) == "暂无天气预报信息"
        assert WeatherTool.format_forecast_info({"forecasts": []}) == "暂无天气预报信息"

    def test_get_dressing_advice_hot(self):
        """测试高温穿搭建议。"""
        weather_data = {
            "lives": [{"temperature": "35", "weather": "晴", "windpower": "2"}]
        }
        result = WeatherTool.get_dressing_advice(weather_data)
        assert "短袖" in result
        assert "防晒" in result

    def test_get_dressing_advice_cold(self):
        """测试低温穿搭建议。"""
        weather_data = {
            "lives": [{"temperature": "5", "weather": "晴", "windpower": "2"}]
        }
        result = WeatherTool.get_dressing_advice(weather_data)
        assert "羽绒服" in result
        assert "保暖" in result

    def test_get_dressing_advice_rainy(self):
        """测试雨天穿搭建议。"""
        weather_data = {
            "lives": [{"temperature": "20", "weather": "小雨", "windpower": "2"}]
        }
        result = WeatherTool.get_dressing_advice(weather_data)
        assert "雨具" in result
        assert "防滑鞋" in result

    def test_get_dressing_advice_windy(self):
        """测试大风天穿搭建议。"""
        weather_data = {
            "lives": [{"temperature": "20", "weather": "晴", "windpower": "5"}]
        }
        result = WeatherTool.get_dressing_advice(weather_data)
        assert "防风外套" in result
