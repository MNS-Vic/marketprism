import os
import asyncio
import unittest
import importlib.util
from pathlib import Path
from aiohttp import web, ClientSession

# project structure: services/monitoring-alerting/tests/integration/test_service.py
# so main.py is two levels up
MODULE_MAIN = Path(__file__).resolve().parents[2] / 'main.py'


def load_service_class():
    spec = importlib.util.spec_from_file_location('monitoring_alerting_main', str(MODULE_MAIN))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore
    return module.MonitoringAlertingService


class ServiceTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._prev_env = {
            'MARKETPRISM_ENABLE_AUTH': os.getenv('MARKETPRISM_ENABLE_AUTH'),
            'MARKETPRISM_ENABLE_VALIDATION': os.getenv('MARKETPRISM_ENABLE_VALIDATION'),
        }

    async def asyncTearDown(self):
        # restore env
        for k, v in self._prev_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    async def _start_service(self):
        ServiceCls = load_service_class()
        service = ServiceCls({'environment': 'test'})

        # build app similar to BaseService.run()
        app = web.Application()
        service.app = app
        # add BaseService default endpoints
        app.router.add_get('/health', service._health_endpoint)  # type: ignore
        app.router.add_get('/metrics', service._metrics_endpoint)  # type: ignore
        # service-specific routes (and optional middlewares)
        service.setup_routes()
        # run on ephemeral port
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        # fetch actual port
        sockets = site._server.sockets  # type: ignore[attr-defined]
        port = sockets[0].getsockname()[1]
        base_url = f'http://127.0.0.1:{port}'
        return service, runner, site, base_url

    async def _stop_service(self, service, runner, site):
        try:
            await service.on_shutdown()
        finally:
            await site.stop()
            await runner.cleanup()


class TestEndpointsNoMiddleware(ServiceTestBase):
    async def test_health_and_metrics_ok(self):
        os.environ['MARKETPRISM_ENABLE_AUTH'] = 'false'
        os.environ['MARKETPRISM_ENABLE_VALIDATION'] = 'false'
        service, runner, site, base_url = await self._start_service()
        try:
            async with ClientSession() as session:
                async with session.get(f'{base_url}/health') as resp:
                    self.assertEqual(resp.status, 200)
                async with session.get(f'{base_url}/metrics') as resp:
                    self.assertEqual(resp.status, 200)
        finally:
            await self._stop_service(service, runner, site)

    async def test_alerts_and_rules_get_post(self):
        os.environ['MARKETPRISM_ENABLE_AUTH'] = 'false'
        os.environ['MARKETPRISM_ENABLE_VALIDATION'] = 'false'
        service, runner, site, base_url = await self._start_service()
        try:
            async with ClientSession() as session:
                # GET alerts
                async with session.get(f'{base_url}/api/v1/alerts') as resp:
                    self.assertEqual(resp.status, 200)
                    data = await resp.json()
                    self.assertIn('alerts', data['data'])
                # POST alert
                payload = {
                    'name': 'test-alert',
                    'severity': 'high',
                    'description': 'for test',
                    'source': 'unittest'
                }
                async with session.post(f'{base_url}/api/v1/alerts', json=payload) as resp:
                    self.assertEqual(resp.status, 200)
                # GET rules
                async with session.get(f'{base_url}/api/v1/alerts/rules') as resp:
                    self.assertEqual(resp.status, 200)
                # POST rule
                rule = {
                    'name': 'test-rule',
                    'description': 'desc',
                    'severity': 'high',
                    'conditions': [{'metric_name': 'cpu_usage_percent', 'operator': 'greater_than', 'threshold': 90, 'duration': 60}]
                }
                async with session.post(f'{base_url}/api/v1/alerts/rules', json=rule) as resp:
                    self.assertEqual(resp.status, 200)
        finally:
            await self._stop_service(service, runner, site)


class TestEndpointsWithMiddleware(ServiceTestBase):
    async def test_auth_enabled_requires_credentials(self):
        os.environ['MARKETPRISM_ENABLE_AUTH'] = 'true'
        os.environ['MARKETPRISM_ENABLE_VALIDATION'] = 'true'
        service, runner, site, base_url = await self._start_service()
        try:
            async with ClientSession() as session:
                # public endpoint: health
                async with session.get(f'{base_url}/health') as resp:
                    self.assertEqual(resp.status, 200)
                # protected endpoint without creds
                async with session.get(f'{base_url}/api/v1/alerts') as resp:
                    self.assertEqual(resp.status, 401)
                # with API key header
                headers = {'X-API-Key': 'mp-monitoring-key-2024'}
                async with session.get(f'{base_url}/api/v1/alerts', headers=headers) as resp:
                    self.assertEqual(resp.status, 200)
        finally:
            await self._stop_service(service, runner, site)



    async def test_login_and_bearer_token_access(self):
        os.environ['MARKETPRISM_ENABLE_AUTH'] = 'true'
        os.environ['MARKETPRISM_ENABLE_VALIDATION'] = 'true'
        service, runner, site, base_url = await self._start_service()
        try:
            async with ClientSession() as session:
                # login to get token
                credentials = {'username': 'admin', 'password': 'marketprism2024!'}
                async with session.post(f'{base_url}/login', json=credentials) as resp:
                    self.assertEqual(resp.status, 200)
                    data = await resp.json()
                    token = data.get('token')
                    self.assertTrue(token)
                # access protected endpoint with bearer token
                headers = {'Authorization': f'Bearer {token}'}
                async with session.get(f'{base_url}/api/v1/alerts', headers=headers) as resp:
                    self.assertEqual(resp.status, 200)
        finally:
            await self._stop_service(service, runner, site)


    async def test_auth_api_key_query_param_access(self):
        os.environ['MARKETPRISM_ENABLE_AUTH'] = 'true'
        os.environ['MARKETPRISM_ENABLE_VALIDATION'] = 'true'
        service, runner, site, base_url = await self._start_service()
        try:
            async with ClientSession() as session:
                # 使用 query 参数 api_key 通过认证
                async with session.get(f'{base_url}/api/v1/alerts?api_key=mp-monitoring-key-2024') as resp:
                    self.assertEqual(resp.status, 200)
        finally:
            await self._stop_service(service, runner, site)

    async def test_validation_rejects_sql_injection_query(self):
        os.environ['MARKETPRISM_ENABLE_AUTH'] = 'true'
        os.environ['MARKETPRISM_ENABLE_VALIDATION'] = 'true'
        service, runner, site, base_url = await self._start_service()
        try:
            async with ClientSession() as session:
                # 先通过认证（API Key 头部）
                headers = {'X-API-Key': 'mp-monitoring-key-2024'}
                # 构造包含 SQL 注入模式的查询参数，期望被 validation 中间件拦截返回 400
                inj = "%27%20OR%201%3D1%20--"  # URL 编码的 ' OR 1=1 --
                async with session.get(f'{base_url}/api/v1/alerts?search={inj}', headers=headers) as resp:
                    self.assertEqual(resp.status, 400)
        finally:
            await self._stop_service(service, runner, site)
