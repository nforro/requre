# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import math
import os
import socket
import unittest
from typing import Optional

import requests

import tests.data.special_requre_module
from requre.cassette import Cassette, StorageMode
from requre.helpers.requests_response import RequestResponseHandling
from requre.simple_object import Simple
from requre.online_replacing import (
    apply_decorator_to_all_methods,
    record,
    record_requests,
    replace_module_match,
)
from tests.data import special_requre_module
from tests.data.special_requre_module import hello


def guard(*args, **kwargs):
    raise IOError("No Internet connection")


original_socket = socket.socket

SELECTOR = str(os.path.basename(__file__).rsplit(".", 1)[0])
TEST_DIR = os.path.dirname(__file__)


def decorator_exact(func):
    def _int():
        return "decorator_c " + func()

    return _int


def decorator_inc(func):
    def _int_inc(a):
        return func(a) + 1

    return _int_inc


@replace_module_match(
    what="tests.data.special_requre_module.hello", decorate=decorator_exact
)
def decorated_exact():
    return tests.data.special_requre_module.hello() + hello() + "exact"


class TestOnlinePatchingModuleMatch(unittest.TestCase):
    def testDecoratorImport(self):
        self.assertEqual(decorated_exact(), "decorator_c Hi! decorator_c Hi! exact")
        # test reverting one decorators
        self.assertEqual(tests.data.special_requre_module.hello(), "Hi! ")
        self.assertEqual(hello(), "Hi! ")

    @replace_module_match(
        what="tests.data.special_requre_module.hello", decorate=decorator_exact
    )
    def testDecoratorMainUsage(self):
        self.assertEqual(tests.data.special_requre_module.hello(), "decorator_c Hi! ")
        self.assertEqual(hello(), "decorator_c Hi! ")
        self.assertEqual(special_requre_module.hello(), "decorator_c Hi! ")

    @replace_module_match(
        what="tests.data.special_requre_module.hello",
        decorate=[decorator_exact, decorator_exact],
    )
    @replace_module_match(
        what="tests.data.special_requre_module.inc", decorate=decorator_inc
    )
    def testDecoratorMultipleDecorators(self):
        self.assertEqual(hello(), "decorator_c decorator_c Hi! ")
        # verify the decorator
        self.assertEqual(decorator_inc(lambda x: x)(1), 2)
        # verify decorated function
        self.assertEqual(tests.data.special_requre_module.inc(1), 3)


# part of documented workaround for the next testcase
setattr(tests.data.special_requre_module.dynamic, "other", lambda self: "static")


class DynamicMethods(unittest.TestCase):
    @replace_module_match(
        what="tests.data.special_requre_module.dynamic.some", decorate=decorator_exact
    )
    def testDynamicClassMethodNotWorking(self):
        self.assertRaises(
            AttributeError, getattr, tests.data.special_requre_module.dynamic, "some"
        )
        self.assertEqual(tests.data.special_requre_module.dynamic().some(), "SOME")

    @unittest.skip("this also does not work, probably caused by pytest execution")
    @replace_module_match(
        what="tests.data.special_requre_module.dynamic.other", decorate=decorator_exact
    )
    def testDynamicClassMethodWorking(self):
        self.assertEqual(
            tests.data.special_requre_module.dynamic().other(), "decorated_c static"
        )


class CassetteSelection(unittest.TestCase):
    def setUp(self) -> None:
        # disable internet access via sockets
        setattr(socket, "socket", guard)

    def reset(self):
        setattr(socket, "socket", original_socket)

    def tearDown(self) -> None:
        self.reset()

    def testGuard(self):
        # check if
        self.assertRaises(IOError, requests.get, "http://example.com")

    @replace_module_match(
        what="requests.sessions.Session.request",
        decorate=RequestResponseHandling.decorator(item_list=["method", "url"]),
    )
    def testWrite(self, cassette: Cassette):
        self.reset()
        response = requests.get("http://example.com")
        self.assertIn("This domain is for use", response.text)
        self.assertFalse(os.path.exists(cassette.storage_file))
        cassette.dump()
        self.assertTrue(os.path.exists(cassette.storage_file))
        os.remove(cassette.storage_file)

    @replace_module_match(
        what="requests.sessions.Session.request",
        decorate=RequestResponseHandling.decorator(item_list=["method", "url"]),
    )
    def testRead(self, cassette: Cassette):
        if cassette.mode == StorageMode.read:
            self.assertTrue(os.path.exists(cassette.storage_file))
        else:
            self.reset()
        response = requests.get("http://example.com")
        self.assertIn("This domain is for use", response.text)

    @replace_module_match(
        what="requests.sessions.Session.request",
        decorate=RequestResponseHandling.decorator(item_list=["method", "url"]),
    )
    @replace_module_match(what="math.sin", decorate=Simple.decorator(item_list=[]))
    def testReadMultiple(self, cassette: Cassette):
        assert cassette
        if cassette.mode == StorageMode.write:
            self.reset()
            sin_output = math.sin(1.5)
        else:
            sin_output = math.sin(4)
        response = requests.get("http://example.com")
        self.assertIn("This domain is for use", response.text)
        self.assertAlmostEqual(0.9974949866040544, sin_output, delta=0.0005)


new_cassette = Cassette()


@apply_decorator_to_all_methods(
    replace_module_match(
        what="math.sin", decorate=Simple.decorator_plain(), cassette=new_cassette
    )
)
@record_requests(cassette=new_cassette)
class DecoratorClassApply(unittest.TestCase):
    # when regeneration, comment lines with assert equals, because checks for equality does not work
    def setUp(self):
        new_cassette.storage_file = None

    def test0(self, cassette: Cassette):
        if cassette.mode == StorageMode.read:
            self.assertEqual(len(new_cassette.storage_object["math"]["sin"]), 1)
        sin_output = math.sin(1.5)
        response = requests.get("http://example.com")
        self.assertIn("This domain is for use", response.text)
        self.assertAlmostEqual(0.9974949866040544, sin_output, delta=0.0005)

    def test1(self):
        sin_output = math.sin(1.5)
        response = requests.get("http://example.com")
        self.assertIn("This domain is for use", response.text)
        self.assertAlmostEqual(0.9974949866040544, sin_output, delta=0.0005)

    def test2(self, cassette: Cassette):
        if cassette.mode == StorageMode.read:
            self.assertEqual(len(new_cassette.storage_object["math"]["sin"]), 2)
        self.test1()
        if cassette.mode == StorageMode.read:
            self.assertEqual(len(new_cassette.storage_object["math"]["sin"]), 1)


@record(what="tests.data.special_requre_module.random_number")
class RecordDecoratorForClass(unittest.TestCase):
    def test_random(self):
        random_number = tests.data.special_requre_module.random_number()
        self.assertEqual(random_number, 0.819349292484907)


@record(what="tests.data.special_requre_module.random_number")
@record(what="tests.data.special_requre_module.another_random_number")
class RecordDecoratorForClassMultiple(unittest.TestCase):
    def test_random(self):
        random_number = tests.data.special_requre_module.random_number()
        another_random_number = tests.data.special_requre_module.another_random_number()
        self.assertEqual(0.6749983968044089, random_number)
        self.assertEqual(0.15676319106079073, another_random_number)


class RecordDecoratorForMethod(unittest.TestCase):
    @record(what="tests.data.special_requre_module.random_number")
    def test_random(self):
        random_number = tests.data.special_requre_module.random_number()
        self.assertEqual(random_number, 0.17583106733657616)


class RecordDecoratorForMethodMultiple(unittest.TestCase):
    @record(what="tests.data.special_requre_module.random_number")
    @record(what="tests.data.special_requre_module.another_random_number")
    def test_random(self):
        random_number = tests.data.special_requre_module.random_number()
        another_random_number = tests.data.special_requre_module.another_random_number()
        self.assertEqual(0.2809709312583647, random_number)
        self.assertEqual(0.039985857086601295, another_random_number)


@record(what="tests.data.special_requre_module.random_number")
class RecordDecoratorForClassCassette(unittest.TestCase):
    cassette: Optional[Cassette]

    def setUp(self) -> None:
        self.setup = False
        self.teardown = False
        self.cassette = None
        super().setUp()

    def cassette_setup(self, cassette: Cassette):
        assert cassette
        self.cassette = cassette
        self.setup = True

    def test_random(self, cassette: Cassette):
        assert cassette
        assert self.setup
        assert not self.teardown
        assert self.cassette == cassette
        random_number = tests.data.special_requre_module.random_number()
        self.assertEqual(random_number, 0.9720986758204466)

    def cassette_teardown(self, cassette: Cassette):
        assert cassette
        assert self.cassette == cassette
        self.teardown = True

    def tearDown(self) -> None:
        assert self.teardown
        super().tearDown()
