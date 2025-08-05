# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Hardware type for DPU (using ipmitool).
"""

from ironic.drivers import generic
from ironic.drivers.modules import ipmitool
from ironic.drivers.modules import noop
from ironic.drivers.modules import noop_mgmt
#from ironic.drivers.modules.dpu import cloud_disk
from ironic.drivers.modules.dpu import boot as dpu_boot
from ironic.drivers.modules import dpu_deploy
from ironic.drivers.modules.storage import dpu_storage

class DpuIPMIToolHardware(generic.GenericHardware):
    """DPU hardware type.

    Uses ``ipmitool`` to implement power and management.
    Provides serial console implementations via ``shellinabox`` or ``socat``.
    """

    @property
    def supported_console_interfaces(self):
        """List of supported console interfaces."""
        return [ipmitool.IPMISocatConsole, ipmitool.IPMIShellinaboxConsole,
                noop.NoConsole]

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [ipmitool.IPMIManagement, noop_mgmt.NoopManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [ipmitool.IPMIPower]

    @property
    def supported_vendor_interfaces(self):
        """List of supported vendor interfaces."""
        return [ipmitool.VendorPassthru, noop.NoVendor]
    
    @property
    def supported_boot_interfaces(self):
        """List of supported boot interfaces."""
        parent_interfaces = super().supported_boot_interfaces
        additional_interfaces = [dpu_boot.DPUBoot]
        return parent_interfaces + additional_interfaces
    
    @property
    def supported_deploy_interfaces(self):
        """List of supported deploy interfaces."""      
        parent_interfaces = super().supported_deploy_interfaces
        additional_interfaces = [dpu_deploy.DpuDeploy]
        return parent_interfaces + additional_interfaces
  
    @property
    def supported_storage_interfaces(self):
        """List of supported storage interfaces."""      
        parent_interfaces = super().supported_storage_interfaces
        additional_interfaces = [dpu_storage.DpuStorage]
        return parent_interfaces + additional_interfaces  
        
    @property
    def supported_cloud_disk_interfaces(self):
        """List of supported cloud disk interfaces."""
        return [cloud_disk.CloudDiskInterface]
