from django.test import TestCase

from common.models import Project

from testreport.models import TestPlan
from testreport.models import Launch
from testreport.models import TestResult
from testreport.models import FAILED
from testreport.models import PASSED


class ProjectTests(TestCase):
    def tearDown(self):
        Project.objects.all().delete()

    def test_creation(self):
        p = Project(name='Test Project 1')
        p.save()
        p1 = Project.objects.get(name__exact='Test Project 1')
        self.assertEqual(p, p1)


class TestPlanTests(TestCase):
    project = None

    def setUp(self):
        self.project = Project(name='Test Project 1')
        self.project.save()

    def tearDown(self):
        Project.objects.all().delete()
        TestPlan.objects.all().delete()

    def test_creation(self):
        tp = TestPlan(name='TestPlan1', project=self.project)
        tp.save()
        tp1 = TestPlan.objects.get(name='TestPlan1')
        self.assertEqual(tp, tp1)

    def test_duplication(self):
        TestPlan.objects.get_or_create(name='TestPlan1', project=self.project)
        TestPlan.objects.get_or_create(name='TestPlan1', project=self.project)
        self.assertEqual(len(TestPlan.objects.all()), 1)


class TestLaunch(TestCase):
    project = None
    tp = None

    def setUp(self):
        self.project = Project(name='Test Project 1')
        self.project.save()
        self.tp = TestPlan(name='Test Project 1', project=self.project)
        self.tp.save()

    def tearDown(self):
        Project.objects.all().delete()
        TestPlan.objects.all().delete()
        Launch.objects.all().delete()

    def test_creation(self):
        url = 'http://2gis.local'
        l = Launch(test_plan=self.tp, started_by=url)
        l.save()
        l1 = self.tp.launch_set.first()
        self.assertEqual(l, l1)
        l1.started_by = url


class TestResultTest(TestCase):
    project = None
    tp = None
    launch = None

    def setUp(self):
        self.project = Project(name='Test Project 1')
        self.project.save()
        self.tp = TestPlan(name='Test Plan 1', project=self.project)
        self.tp.save()
        self.launch = Launch(test_plan=self.tp)
        self.launch.save()

    def tearDown(self):
        Project.objects.all().delete()
        TestPlan.objects.all().delete()
        Launch.objects.all().delete()

    def test_creation(self):
        r = TestResult(launch=self.launch, name='TestCase1', suite='TestSute1',
                       state=FAILED,
                       failure_reason='Very clear message about failure',
                       duration=1)
        r1 = TestResult(launch=self.launch, name='TestCase1',
                        suite='TestSute2',
                        state=PASSED,
                        failure_reason='Very clear message about failure',
                        duration=1)
        r.save()
        r1.save()
        self.assertEqual(len(self.launch.testresult_set.all()), 2)
