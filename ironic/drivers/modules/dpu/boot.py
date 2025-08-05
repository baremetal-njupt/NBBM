from ironic.common import states
from ironic.conductor import utils as manager_utils
from ironic.common import boot_devices
from oslo_log import log as logging
from ironic.drivers import base


LOG = logging.getLogger(__name__)


class DPUBoot(base.BootInterface):
    """DPUToolBoot implementation of BootInterface."""

    def get_properties(self):
        """Return the properties of the interface."""
        return {}  

    def validate(self, task):
        """Validate the driver-specific Node deployment info."""
        pass  # nothing to do

    def prepare_ramdisk(self, task, ramdisk_params):
        """Prepares the boot of Ironic ramdisk."""
        pass  # nothing to do

    def clean_up_ramdisk(self, task):
        """Cleans up the boot of ironic ramdisk."""
        pass  # nothing to do

    def prepare_instance(self, task):
        """Prepares the boot of instance."""
        pass  # nothing to do

    def prepare_instance(self, task):
        """Prepares the instance for booting.
    
        If the node's provision state is not ACTIVE, the node will be set to boot 
        from the disk.
    
        :param task: a task from TaskManager.
        :returns: None
        """
        # Ensure the task and its node attribute are valid
        if not task or not hasattr(task, 'node'):
            LOG.error("Invalid task passed to prepare_instance.")
            return
    
        node_provision_state = getattr(task.node, 'provision_state', None)
    
        if not node_provision_state:
            LOG.warning("Could not retrieve provision state for the node.")
            return
    
        boot_device = boot_devices.DISK
    
        # If node's provision state is not ACTIVE, set it to boot from the disk
        if node_provision_state != states.ACTIVE:
            manager_utils.node_set_boot_device(task, boot_device, persistent=True)
            LOG.debug("Node %(node)s is set to boot from %(device)s.", 
                      {'node': task.node.uuid, 'device': boot_device})
        else:
            LOG.warning("Node %(node)s boot preparation skipped as it's already in ACTIVE state.", 
                      {'node': task.node.uuid})


    def clean_up_instance(self, task):
        """Cleans up the boot of instance."""
        pass  # nothing to do

    def validate_rescue(self, task):
        """Validate that the node has required properties for rescue."""
        pass  # nothing to do

    def validate_inspection(self, task):
        """Validate that the node has required properties for inspection."""
        pass  # nothing to do
