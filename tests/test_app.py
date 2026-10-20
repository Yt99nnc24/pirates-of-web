"""Integration checks against isolated temporary SQLite databases."""
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app import create_app


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(__file__).parent / ('.data-' + uuid.uuid4().hex)
        self.temp.mkdir()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only',
                               'DATABASE': str(self.temp / 'test.db'), 'ENABLE_DEMO': True})
        self.client = self.app.test_client()

    def tearDown(self):
        (self.temp / 'test.db').unlink(missing_ok=True)
        self.temp.rmdir()

    def post(self, client, path, data=None):
        client.get('/')
        with client.session_transaction() as state:
            token = state['csrf']
        return client.post(path, data={**(data or {}), 'csrf_token': token}, follow_redirects=True)

    def signup(self, client, role, email, department='General medicine'):
        return self.post(client, '/' + role + '-login', dict(action='signup', name='Test Person', email=email,
                         password='test-password', department=department, specialization='General practice'))

    def login(self, client, role, email):
        return self.post(client, '/' + role + '-login', dict(email=email, password='test-password'))

    def approve(self, email):
        result = self.app.test_cli_runner().invoke(args=['approve-doctor', email])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_pages_and_csrf(self):
        for path in ('/', '/patient-login', '/doctor-login', '/patient-login?action=signup', '/doctor-login?action=signup', '/static/style.css', '/static/app.js'):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200, path)
        self.assertEqual(self.client.post('/patient-login').status_code, 400)
        self.assertEqual(self.client.get('/missing').status_code, 404)
        self.assertEqual(self.client.get('/patient').status_code, 302)
        self.assertEqual(self.client.get('/doctor').status_code, 302)

    def test_full_consultation_and_access_boundaries(self):
        patient, other, doctor = self.client, self.app.test_client(), self.app.test_client()
        self.signup(patient, 'patient', 'one@example.test')
        self.login(patient, 'patient', 'one@example.test')
        self.assertEqual(patient.get('/doctor').status_code, 403)
        page = self.post(patient, '/cases', {'department': 'General medicine', 'symptoms': 'Fictional concern about my sleep routine.'})
        self.assertIn(b'Case submitted', page.data)
        self.signup(other, 'patient', 'two@example.test')
        self.login(other, 'patient', 'two@example.test')
        self.assertNotIn(b'Fictional concern about my sleep routine.', other.get('/patient').data)
        self.signup(doctor, 'doctor', 'doctor@example.test')
        self.assertIn(b'awaiting administrator approval', self.login(doctor, 'doctor', 'doctor@example.test').data)
        self.approve('doctor@example.test')
        self.assertIn(b'Fictional concern', self.login(doctor, 'doctor', 'doctor@example.test').data)
        self.assertEqual(doctor.get('/patient').status_code, 403)
        page = self.post(doctor, '/cases/1/review', {'notes': 'Fictional review: discuss the routine during consultation.'})
        self.assertIn(b'Review saved', page.data)
        self.assertIn(b'Fictional review:', patient.get('/patient').data)
        self.assertIn(b'already been reviewed', self.post(doctor, '/cases/1/review', {'notes': 'Overwrite attempt'}).data)
        different = self.app.test_client()
        self.signup(different, 'doctor', 'dental@example.test', 'Dental care')
        self.approve('dental@example.test')
        self.login(different, 'doctor', 'dental@example.test')
        self.assertNotIn(b'Fictional concern', different.get('/doctor').data)
        self.assertEqual(self.post(different, '/cases/1/review', {'notes': 'Forbidden review'}).status_code, 403)

    def test_validation_and_escaping(self):
        self.signup(self.client, 'patient', 'p@example.test')
        duplicate = self.signup(self.client, 'patient', 'p@example.test')
        self.assertIn(b'already registered', duplicate.data)
        self.assertIn(b'incorrect', self.post(self.client, '/patient-login', {'email':'p@example.test', 'password':'wrong'}).data)
        self.login(self.client, 'patient', 'p@example.test')
        self.assertIn(b'10', self.post(self.client, '/cases', {'department': 'Dental care', 'symptoms':'bad'}).data)
        self.assertIn(b'Choose a department', self.post(self.client, '/cases', {'department':'invalid', 'symptoms':'Long fictional concern'}).data)
        page = self.post(self.client, '/cases', {'department':'Dental care', 'symptoms':'<script>alert(1)</script>'})
        self.assertNotIn(b'<script>alert(1)</script>', page.data)
        self.assertIn(b'&lt;script&gt;', page.data)
        with sqlite3.connect(self.app.config['DATABASE']) as conn:
            password_hash = conn.execute('SELECT password_hash FROM users').fetchone()[0]
            self.assertNotEqual(password_hash, 'test-password')
        conn.close()

    def test_demo_workspace_isolation(self):
        self.post(self.client, '/demo/patient')
        self.post(self.client, '/logout')
        self.assertIn(b'sleep routine', self.post(self.client, '/demo/doctor').data)
        outsider = self.app.test_client()
        self.assertNotIn(b'sleep routine', self.post(outsider, '/demo/doctor').data)
        self.assertEqual(self.post(outsider, '/cases/1/review', {'notes':'Forbidden demo review'}).status_code, 403)
        self.app.config['ENABLE_DEMO'] = False
        self.assertEqual(self.post(outsider, '/demo/patient').status_code, 404)

    def test_malformed_csrf_and_email_are_rejected(self):
        self.client.get('/patient-login')
        for token in ('wrong-token', '\u0905\u092e\u093e\u0928\u094d\u092f'):
            response = self.client.post('/patient-login', data={'csrf_token': token})
            self.assertEqual(response.status_code, 400)
        for email in ('missing-domain@', 'two@@example.test', 'a b@example.test', 'a@example'):
            response = self.signup(self.client, 'patient', email)
            self.assertIn(b'Enter a valid email', response.data)
        with sqlite3.connect(self.app.config['DATABASE']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)
        conn.close()


if __name__ == '__main__':
    unittest.main()
