# Copyright 2015 Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import six
import time
from oslo_log import log as logging

from tempest.common import custom_matchers
from tempest.common.utils.linux import remote_client
from tempest import config
from tempest import exceptions
from tempest.scenario import manager
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class TestCloudVScenario(manager.ScenarioTest):

    """ This is a Cloud Validation scenario test.
    """

    def _wait_for_server_status(self, status):
        server_id = self.server['id']
        # Raise on error defaults to True, which is consistent with the
        # original function from scenario tests here
        self.servers_client.wait_for_server_status(server_id, status)

    def glance_image_create(self):
        img_path = "/home/ikhudoshyn/glance.qcow2"
        img_container_format = "bare"
        img_disk_format = "qcow2"
        LOG.debug("paths: img: %s, container_fomat: %s, disk_format: %s " %
                  (img_path, img_container_format, img_disk_format))
        self.image = self._image_create('mcv-scenario-img',
                                        img_container_format,
                                        img_path,
                                        disk_format=img_disk_format)
        LOG.debug("image:%s" % self.image)

    def nova_boot(self):
        self.server = self.create_server(image=self.image, flavor=3)

    def create_and_add_security_group(self):
        secgroup = self._create_security_group()
        self.servers_client.add_security_group(self.server['id'],
                                               secgroup['name'])
        self.addCleanup(self.servers_client.remove_security_group,
                        self.server['id'], secgroup['name'])

        def wait_for_secgroup_add():
            body = self.servers_client.get_server(self.server['id'])
            return {'name': secgroup['name']} in body['security_groups']

        if not test.call_until_true(wait_for_secgroup_add,
                                    CONF.compute.build_timeout,
                                    CONF.compute.build_interval):
            msg = ('Timed out waiting for adding security group %s to server '
                   '%s' % (secgroup['id'], self.server['id']))
            raise exceptions.TimeoutException(msg)

    def get_remote_client(self, server_or_ip, username=None, password=None):
        """Get a SSH client to a remote server

        @param server_or_ip a server object as returned by Tempest compute
            client or an IP address to connect to
        @param username name of the Linux account on the remote server
        @param password password for the Linux account on the remote server
        @return a RemoteClient object
        """
        if isinstance(server_or_ip, six.string_types):
            ip = server_or_ip
        else:
            addrs = server_or_ip['addresses'][CONF.compute.network_for_ssh]
            try:
                ip = (addr['addr'] for addr in addrs if
                      netaddr.valid_ipv4(addr['addr'])).next()
            except StopIteration:
                raise lib_exc.NotFound("No IPv4 addresses to use for SSH to "
                                       "remote server.")

        linux_client = remote_client.RemoteClient(ip, username,
                                                  password=password)
        # default timeout is set via CONF.compute.ssh_timeout
        # we override it here since we expect lenghtier operations
        linux_client.ssh_client.timeout = 1200

        try:
            linux_client.validate_authentication()
        except Exception as e:
            message = ('Initializing SSH connection to %(ip)s failed. '
                       'Error: %(error)s' % {'ip': ip, 'error': e})
            LOG.exception(message)
            raise

        return linux_client

    @test.idempotent_id('bdbb5441-9204-419d-a225-999999999999')
    @test.services('cloudv')
    def test_cloudv_scenario(self):
        self.glance_image_create()
        self.nova_boot()

        self.floating_ip = self.create_floating_ip(self.server)
        self.create_and_add_security_group()

        self.linux_client = self.get_remote_client(self.floating_ip['ip'],
                                                   username="mcv",
                                                   password="mcv")
