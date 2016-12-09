
import unittest
import jinja2

import browsepy.extensions


class TestCompressBase(unittest.TestCase):
    extension = browsepy.extensions.CompressExtension
    filename = 'test'

    def setUp(self):
        self.env = jinja2.Environment(
            autoescape=True,
            extensions=[self.extension]
            )

    def render(self, html, **kwargs):
        env = self.env
        globals = env.make_globals(None)
        code = env.compile(html, name=self.filename, filename=self.filename)
        template = env.template_class.from_code(env, code, globals, None)
        return template.render(**kwargs)


class TestHTMLCompress(TestCompressBase):
    extension = browsepy.extensions.HTMLCompress
    filename = 'test.html'

    def test_compress(self):
        html = self.render('''
            <html>
              <head>
                <title>{{ title }}</title>
              </head>
              <body
               class="{{css}} prop"
               >
                <em><b>a</b>    <i> b</i></em>
                {% if a %}b{% endif %}
              </body>
            </html>
            ''', title=42, href='index.html', css='t', a=True)
        self.assertEqual(
            html,
            '<html><head><title>42</title></head><body class="t prop">'
            '<em><b>a</b><i> b</i></em>b'
            '</body></html>'
            )

    def test_ignored_content(self):
        html = self.render(
            '<script\ndata-a >\n <a>   <a> asdf </script>\n<br> <br>'
            )
        self.assertEqual(
            html,
            '<script data-a>\n <a>   <a> asdf </script><br><br>'
            )

    def test_cdata(self):
        html = self.render(
            '<![CDATA[\n<a>   <br>\n]]>\n<a>   <br>\n'
            )
        self.assertEqual(
            html,
            '<![CDATA[\n<a>   <br>\n]]><a><br>'
            )

    def test_broken(self):
        html = self.render('<script>\n <a>   <a> asdf ')
        self.assertEqual(html, '<script>\n <a>   <a> asdf ')


class TestJSONCompress(TestCompressBase):
    extension = browsepy.extensions.JSONCompress
    filename = 'test.json'

    def test_compress(self):
        json = self.render('''
            {
                "a": {{ a }},
                "b": "this is a \\"{{ title }}\\"",
                "c": -1e2
            }
            ''', title=42, a=True)
        self.assertEqual(json, '{"a":True,"b":"this is a \\"42\\"","c":-1e2}')
