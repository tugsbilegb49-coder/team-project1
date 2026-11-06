from unittest.mock import patch
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from .auth import LoginIPThrottle


class HealthAndProxyTests(TestCase):
    def test_health_is_public_and_checks_dependencies(self):
        client=APIClient()
        self.assertEqual(client.get('/api/health/').status_code,200)
        with patch('users.health.cache.get',return_value=None),self.assertLogs('users.health',level='ERROR'):
            response=client.get('/api/health/')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.data,{'status':'unavailable'})

    @override_settings(TRUSTED_PROXY_NETWORKS=['172.30.0.2/32'])
    def test_forwarded_ip_is_used_only_for_explicit_proxy(self):
        from rest_framework.test import APIRequestFactory
        factory=APIRequestFactory()
        throttle=LoginIPThrottle()
        trusted=factory.post('/',REMOTE_ADDR='172.30.0.2',HTTP_X_FORWARDED_FOR='203.0.113.9')
        untrusted=factory.post('/',REMOTE_ADDR='198.51.100.9',HTTP_X_FORWARDED_FOR='203.0.113.9')
        self.assertIn('203.0.113.9',throttle.get_cache_key(trusted,None))
        self.assertIn('198.51.100.9',throttle.get_cache_key(untrusted,None))
