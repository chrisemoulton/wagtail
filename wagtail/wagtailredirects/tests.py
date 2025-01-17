from django.test import TestCase
from wagtail.wagtailredirects import models
from wagtail.wagtailcore.models import Page, Site
from wagtail.tests.utils import WagtailTestUtils
from django.core.urlresolvers import reverse


class TestRedirects(TestCase):
    fixtures = ['test.json']

    def test_path_normalisation(self):
        # Shortcut to normalise function (to keep things tidy)
        normalise_path = models.Redirect.normalise_path

        # Create a path
        path = normalise_path('/Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2')

        # Test against equivalant paths
        self.assertEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # The exact same URL
        self.assertEqual(path, normalise_path('http://mywebsite.com:8000/Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # Scheme, hostname and port ignored
        self.assertEqual(path, normalise_path('Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # Leading slash can be omitted
        self.assertEqual(path, normalise_path('Hello/world.html/;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # Trailing slashes are ignored
        self.assertEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2#cool'))  # Fragments are ignored
        self.assertEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=five?Baz=quux2&foo=Bar'))  # Order of query string parameters is ignored
        self.assertEqual(path, normalise_path('/Hello/world.html;buzz=five;fizz=three?foo=Bar&Baz=quux2'))  # Order of parameters is ignored
        self.assertEqual(path, normalise_path('  /Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # Leading whitespace
        self.assertEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2  '))  # Trailing whitespace

        # Test against different paths
        self.assertNotEqual(path, normalise_path('/hello/world.html;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # 'hello' is lowercase
        self.assertNotEqual(path, normalise_path('/Hello/world;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # No '.html'
        self.assertNotEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=five?foo=bar&Baz=Quux2'))  # Query string parameter value has wrong case
        self.assertNotEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=five?foo=Bar&baz=quux2'))  # Query string parameter name has wrong case
        self.assertNotEqual(path, normalise_path('/Hello/world.html;fizz=three;buzz=Five?foo=Bar&Baz=quux2'))  # Parameter value has wrong case
        self.assertNotEqual(path, normalise_path('/Hello/world.html;Fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # Parameter name has wrong case
        self.assertNotEqual(path, normalise_path('/Hello/world.html?foo=Bar&Baz=quux2'))  # Missing params
        self.assertNotEqual(path, normalise_path('/Hello/WORLD.html;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # 'WORLD' is uppercase
        self.assertNotEqual(path, normalise_path('/Hello/world.htm;fizz=three;buzz=five?foo=Bar&Baz=quux2'))  # '.htm' is not the same as '.html'

        # Normalise some rubbish to make sure it doesn't crash
        normalise_path('This is not a URL')
        normalise_path('//////hello/world')
        normalise_path('!#@%$*')
        normalise_path('C:\\Program Files (x86)\\Some random program\\file.txt')

    def test_basic_redirect(self):
        # Create a redirect
        redirect = models.Redirect(old_path='/redirectme', redirect_link='/redirectto')
        redirect.save()

        # Navigate to it
        response = self.client.get('/redirectme/')

        # Check that we were redirected
        self.assertRedirects(response, '/redirectto', status_code=301, fetch_redirect_response=False)

    def test_temporary_redirect(self):
        # Create a redirect
        redirect = models.Redirect(old_path='/redirectme', redirect_link='/redirectto', is_permanent=False)
        redirect.save()

        # Navigate to it
        response = self.client.get('/redirectme/')

        # Check that we were redirected temporarily
        self.assertRedirects(response, '/redirectto', status_code=302, fetch_redirect_response=False)

    def test_redirect_stripping_query_string(self):
        # Create a redirect which includes a query string
        redirect_with_query_string = models.Redirect(old_path='/redirectme?foo=Bar', redirect_link='/with-query-string-only')
        redirect_with_query_string.save()

        # ... and another redirect without the query string
        redirect_without_query_string = models.Redirect(old_path='/redirectme', redirect_link='/without-query-string')
        redirect_without_query_string.save()

        # Navigate to the redirect with the query string
        r_matching_qs = self.client.get('/redirectme/?foo=Bar')
        self.assertRedirects(r_matching_qs, '/with-query-string-only', status_code=301, fetch_redirect_response=False)

        # Navigate to the redirect with a different query string
        # This should strip out the query string and match redirect_without_query_string
        r_no_qs = self.client.get('/redirectme/?utm_source=irrelevant')
        self.assertRedirects(r_no_qs, '/without-query-string', status_code=301, fetch_redirect_response=False)

    def test_redirect_to_page(self):
        christmas_page = Page.objects.get(url_path='/home/events/christmas/')
        models.Redirect.objects.create(old_path='/xmas', redirect_page=christmas_page)

        response = self.client.get('/xmas/', HTTP_HOST='test.example.com')
        self.assertRedirects(response, 'http://test.example.com/events/christmas/', status_code=301, fetch_redirect_response=False)

    def test_redirect_from_any_site(self):
        contact_page = Page.objects.get(url_path='/home/contact-us/')
        Site.objects.create(hostname='other.example.com', port=80, root_page=contact_page)

        christmas_page = Page.objects.get(url_path='/home/events/christmas/')
        models.Redirect.objects.create(old_path='/xmas', redirect_page=christmas_page)

        # no site was specified on the redirect, so it should redirect regardless of hostname
        response = self.client.get('/xmas/', HTTP_HOST='localhost')
        self.assertRedirects(response, 'http://localhost/events/christmas/', status_code=301, fetch_redirect_response=False)

        response = self.client.get('/xmas/', HTTP_HOST='other.example.com')
        self.assertRedirects(response, 'http://localhost/events/christmas/', status_code=301, fetch_redirect_response=False)

    def test_redirect_from_specific_site(self):
        contact_page = Page.objects.get(url_path='/home/contact-us/')
        other_site = Site.objects.create(hostname='other.example.com', port=80, root_page=contact_page)

        christmas_page = Page.objects.get(url_path='/home/events/christmas/')
        models.Redirect.objects.create(old_path='/xmas', redirect_page=christmas_page, site=other_site)

        # redirect should only respond when site is other_site
        response = self.client.get('/xmas/', HTTP_HOST='other.example.com')
        self.assertRedirects(response, 'http://localhost/events/christmas/', status_code=301, fetch_redirect_response=False)

        response = self.client.get('/xmas/', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 404)


class TestRedirectsIndexView(TestCase, WagtailTestUtils):
    def setUp(self):
        self.login()

    def get(self, params={}):
        return self.client.get(reverse('wagtailredirects:index'), params)

    def test_simple(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'wagtailredirects/index.html')

    def test_search(self):
        response = self.get({'q': "Hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['query_string'], "Hello")

    def test_pagination(self):
        pages = ['0', '1', '-1', '9999', 'Not a page']
        for page in pages:
            response = self.get({'p': page})
            self.assertEqual(response.status_code, 200)


class TestRedirectsAddView(TestCase, WagtailTestUtils):
    fixtures = ['test.json']

    def setUp(self):
        self.login()

    def get(self, params={}):
        return self.client.get(reverse('wagtailredirects:add'), params)

    def post(self, post_data={}):
        return self.client.post(reverse('wagtailredirects:add'), post_data)

    def test_simple(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'wagtailredirects/add.html')

    def test_add(self):
        response = self.post({
            'old_path': '/test',
            'site': '',
            'is_permanent': 'on',
            'redirect_link': 'http://www.test.com/',
        })

        # Should redirect back to index
        self.assertRedirects(response, reverse('wagtailredirects:index'))

        # Check that the redirect was created
        redirects = models.Redirect.objects.filter(old_path='/test')
        self.assertEqual(redirects.count(), 1)
        self.assertEqual(redirects.first().redirect_link, 'http://www.test.com/')
        self.assertEqual(redirects.first().site, None)

    def test_add_with_site(self):
        localhost = Site.objects.get(hostname='localhost')
        response = self.post({
            'old_path': '/test',
            'site': localhost.id,
            'is_permanent': 'on',
            'redirect_link': 'http://www.test.com/',
        })

        # Should redirect back to index
        self.assertRedirects(response, reverse('wagtailredirects:index'))

        # Check that the redirect was created
        redirects = models.Redirect.objects.filter(old_path='/test')
        self.assertEqual(redirects.count(), 1)
        self.assertEqual(redirects.first().redirect_link, 'http://www.test.com/')
        self.assertEqual(redirects.first().site, localhost)

    def test_add_validation_error(self):
        response = self.post({
            'old_path': '',
            'site': '',
            'is_permanent': 'on',
            'redirect_link': 'http://www.test.com/',
        })

        # Should not redirect to index
        self.assertEqual(response.status_code, 200)

    def test_cannot_add_duplicate_with_no_site(self):
        models.Redirect.objects.create(old_path='/test', site=None, redirect_link='http://elsewhere.com/')
        response = self.post({
            'old_path': '/test',
            'site': '',
            'is_permanent': 'on',
            'redirect_link': 'http://www.test.com/',
        })

        # Should not redirect to index
        self.assertEqual(response.status_code, 200)

    def test_cannot_add_duplicate_on_same_site(self):
        localhost = Site.objects.get(hostname='localhost')
        models.Redirect.objects.create(old_path='/test', site=localhost, redirect_link='http://elsewhere.com/')
        response = self.post({
            'old_path': '/test',
            'site': localhost.pk,
            'is_permanent': 'on',
            'redirect_link': 'http://www.test.com/',
        })

        # Should not redirect to index
        self.assertEqual(response.status_code, 200)

    def test_can_reuse_path_on_other_site(self):
        localhost = Site.objects.get(hostname='localhost')
        contact_page = Page.objects.get(url_path='/home/contact-us/')
        other_site = Site.objects.create(hostname='other.example.com', port=80, root_page=contact_page)

        models.Redirect.objects.create(old_path='/test', site=localhost, redirect_link='http://elsewhere.com/')
        response = self.post({
            'old_path': '/test',
            'site': other_site.pk,
            'is_permanent': 'on',
            'redirect_link': 'http://www.test.com/',
        })

        # Should redirect back to index
        self.assertRedirects(response, reverse('wagtailredirects:index'))

        # Check that the redirect was created
        redirects = models.Redirect.objects.filter(redirect_link='http://www.test.com/')
        self.assertEqual(redirects.count(), 1)


class TestRedirectsEditView(TestCase, WagtailTestUtils):
    def setUp(self):
        # Create a redirect to edit
        self.redirect = models.Redirect(old_path='/test', redirect_link='http://www.test.com/')
        self.redirect.save()

        # Login
        self.login()

    def get(self, params={}, redirect_id=None):
        return self.client.get(reverse('wagtailredirects:edit', args=(redirect_id or self.redirect.id, )), params)

    def post(self, post_data={}, redirect_id=None):
        return self.client.post(reverse('wagtailredirects:edit', args=(redirect_id or self.redirect.id, )), post_data)

    def test_simple(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'wagtailredirects/edit.html')

    def test_nonexistant_redirect(self):
        self.assertEqual(self.get(redirect_id=100000).status_code, 404)

    def test_edit(self):
        response = self.post({
            'old_path': '/test',
            'is_permanent': 'on',
            'site': '',
            'redirect_link': 'http://www.test.com/ive-been-edited',
        })

        # Should redirect back to index
        self.assertRedirects(response, reverse('wagtailredirects:index'))

        # Check that the redirect was edited
        redirects = models.Redirect.objects.filter(old_path='/test')
        self.assertEqual(redirects.count(), 1)
        self.assertEqual(redirects.first().redirect_link, 'http://www.test.com/ive-been-edited')
        self.assertEqual(redirects.first().site, None)

    def test_edit_with_site(self):
        localhost = Site.objects.get(hostname='localhost')

        response = self.post({
            'old_path': '/test',
            'is_permanent': 'on',
            'site': localhost.id,
            'redirect_link': 'http://www.test.com/ive-been-edited',
        })

        # Should redirect back to index
        self.assertRedirects(response, reverse('wagtailredirects:index'))

        # Check that the redirect was edited
        redirects = models.Redirect.objects.filter(old_path='/test')
        self.assertEqual(redirects.count(), 1)
        self.assertEqual(redirects.first().redirect_link, 'http://www.test.com/ive-been-edited')
        self.assertEqual(redirects.first().site, localhost)

    def test_edit_validation_error(self):
        response = self.post({
            'old_path': '',
            'is_permanent': 'on',
            'site': '',
            'redirect_link': 'http://www.test.com/ive-been-edited',
        })

        # Should not redirect to index
        self.assertEqual(response.status_code, 200)

    def test_edit_duplicate(self):
        models.Redirect.objects.create(old_path='/othertest', site=None, redirect_link='http://elsewhere.com/')
        response = self.post({
            'old_path': '/othertest',
            'is_permanent': 'on',
            'site': '',
            'redirect_link': 'http://www.test.com/ive-been-edited',
        })

        # Should not redirect to index
        self.assertEqual(response.status_code, 200)


class TestRedirectsDeleteView(TestCase, WagtailTestUtils):
    def setUp(self):
        # Create a redirect to edit
        self.redirect = models.Redirect(old_path='/test', redirect_link='http://www.test.com/')
        self.redirect.save()

        # Login
        self.login()

    def get(self, params={}, redirect_id=None):
        return self.client.get(reverse('wagtailredirects:delete', args=(redirect_id or self.redirect.id, )), params)

    def post(self, post_data={}, redirect_id=None):
        return self.client.post(reverse('wagtailredirects:delete', args=(redirect_id or self.redirect.id, )), post_data)

    def test_simple(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'wagtailredirects/confirm_delete.html')

    def test_nonexistant_redirect(self):
        self.assertEqual(self.get(redirect_id=100000).status_code, 404)

    def test_delete(self):
        response = self.post({
            'hello': 'world'
        })

        # Should redirect back to index
        self.assertRedirects(response, reverse('wagtailredirects:index'))

        # Check that the redirect was deleted
        redirects = models.Redirect.objects.filter(old_path='/test')
        self.assertEqual(redirects.count(), 0)
