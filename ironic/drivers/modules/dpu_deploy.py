from oslo_log import log as logging
from ironic.common import exception
from ironic.common import states
from ironic.conductor import utils as manager_utils
from ironic.drivers import base
from ironic.common.i18n import _
from ironic.common import states
from ironic.common import utils
from ironic.drivers.modules import deploy_utils
from ironic.common import dhcp_factory
#from ironic.drivers.modules.storage import dpu_storage as storage
from ironic.drivers.modules import agent_base
from ironic_lib import metrics_utils
from ironic.conductor import task_manager
from ironic.drivers.modules import ipmitool
import time

LOG = logging.getLogger(__name__)

METRICS = metrics_utils.get_metrics_logger(__name__)

class AgentDeployMixin(agent_base.AgentDeployMixin):

    @METRICS.timer('AgentDeployMixin.continue_deploy')
    @task_manager.require_exclusive_lock
    def continue_deploy(self, task):
        pass

#class DpuDeploy(AgentDeployMixin, base.DeployInterface):
class DpuDeploy(base.DeployInterface):
    """DPU Deployment implementation."""
  
  
  
    def get_properties(self):
        return agent_base.VENDOR_PROPERTIES  
        
        
    @METRICS.timer('DpuDeploy.validate')
    def validate(self, task):
        """Validate the deployment information for the task's node.

        :param task: a TaskManager instance containing the node to act on.
        :raises: InvalidParameterValue.
        :raises: MissingParameterValue
        """
        task.driver.boot.validate(task)
        node = task.node

        # Check the boot_mode, boot_option and disk_label capabilities values.
        deploy_utils.validate_capabilities(node)

        # Edit early if we are not writing a volume as the validate
        # tasks evaluate root device hints.
        if not task.driver.storage.should_write_image(task):
            LOG.debug('Skipping complete deployment interface validation '
                      'for node %s as it is set to boot from a remote '
                      'volume.', node.uuid)
            return

        # TODO(rameshg87): iscsi_ilo driver used to call this function. Remove
        # and copy-paste it's contents here.
        # validate(task)
        
             
    def simple_node_power_reset(self, task):

        try:
            driver_info = ipmitool._parse_driver_info(task.node)
            ipmitool._exec_ipmitool(driver_info, "power reset")
            
        except Exception as e:
            LOG.error("Power reset failed for node %(node)s with error: %(error)s",
                      {'node': task.node.uuid, 'error': e})
        else:
            LOG.info("Successfully reset power for node %(node)s",
                     {'node': task.node.uuid})    
                     

    @METRICS.timer('DpuDeploy.deploy')   
    @base.deploy_step(priority=100)
    @task_manager.require_exclusive_lock        
    def deploy(self, task):
        """Start deployment of the task's node.
        :param task: a TaskManager instance containing the node to act on.
        :returns: deploy state DEPLOYWAIT.
        """
        LOG.info('Initiating deployment for node %(node_id)s with target volumes: %(volumes)s', 
                 {'node_id': task.node.uuid, 'volumes': task.volume_targets})
        node = task.node
                
        dpu_ipaddr = node.extra.get('dpu').get('ip_addr')
        if not dpu_ipaddr:
            raise ValueError("Missing IP address for DPU.")
            
        heartbeat_verified = task.driver.storage.check_heartbeat(dpu_ipaddr)
        if not heartbeat_verified:
            raise exception.StorageError(f"Heartbeat check failed for IP {dpu_ipaddr}.")

        cap = node.properties.get('capabilities')
        
        if 'dpu_boot' in cap:
            
            # Call storage interface to attach volumes
            try:
                connected_volumes = task.driver.storage.attach_volumes(task) 
            except exception.StorageError as e:
                raise exception.InstanceDeployFailure(_("Encountered an issue while trying to attach volumes to node %(node_uuid)s: %(err)s") %
                                                      {'node_uuid': node.uuid, 'err': e})
            
            if not connected_volumes:
                raise exception.InstanceDeployFailure(_("Node %(node_uuid)s has no volumes attached post-operation.") %
                                                      {'node_uuid': node.uuid})
            
            #time.sleep(30)
            time.sleep(5)

            LOG.info('Successfully completed attach_volumes for node %s', node.uuid)
            
            task.driver.network.remove_provisioning_network(task)
            task.driver.network.configure_tenant_networks(task)
            
            LOG.info('Successfully completed network operations for node %s', node.uuid)
            
            
            task.driver.boot.prepare_instance(task)
            LOG.info('Start SOFT_REBOOT for node %s', node.uuid)
            
            self.simple_node_power_reset(task)
            #manager_utils.node_power_action(task, states.REBOOT)
            LOG.info('Successfully completed REBOOT for node %s', node.uuid)
            
            #task.process_event('done')
            LOG.info('start_console for node %s', node.uuid)
            #task.driver.console.start_console(task) 
            LOG.info('Successfully completed deployment for node %s', node.uuid)
            
            return None
    
        else:
            raise exception.InstanceDeployFailure(_("Node %(node_uuid)s lacks the capability for dpu_boot.") %
                                                  {'node_uuid': node.uuid})

        
    @METRICS.timer('DpuDeploy.tear_down')
    def tear_down(self, task):
        """Tear down a previous deployment on the task's node.
        ...
        """
        LOG.info('Initiating teardown for node %(node_id)s with attached volumes: %(volumes)s',
                 {'node_id': task.node.uuid, 'volumes': task.volume_targets})
        node = task.node
        
        dpu_ipaddr = node.extra.get('dpu').get('ip_addr')
        if not dpu_ipaddr:
            raise ValueError("Missing IP address for DPU.")
        
        heartbeat_verified = task.driver.storage.check_heartbeat(dpu_ipaddr)
        if not heartbeat_verified:
            raise exception.StorageError(f"Heartbeat check failed for IP {dpu_ipaddr}.")
        
        cap = node.properties.get('capabilities')
        
        if 'dpu_boot' in cap:
            # Call storage interface to detach volumes
            try:
                task.driver.storage.detach_volumes(task)
                heartbeat_verified = task.driver.storage.check_heartbeat(dpu_ipaddr)
            except exception.StorageError as e:
                raise exception.InstanceDeployFailure(_("Encountered an issue while trying to detach volumes from node %(node_uuid)s: %(err)s") %
                                                      {'node_uuid': node.uuid, 'err': e})
                                                      
            LOG.info('Successfully completed deattach_volumes for node %s', node.uuid)  
            
            # Other teardown operations
            LOG.info('Start other teardown operations for node %s', node.uuid)
            deploy_utils.tear_down_storage_configuration(task)
            with manager_utils.power_state_for_network_configuration(task):
                task.driver.network.unconfigure_tenant_networks(task)
                # NOTE(mgoddard): If the deployment was unsuccessful the node may
                # have ports on the provisioning network which were not deleted.
                task.driver.network.remove_provisioning_network(task)
            LOG.info('Successfully completed other teardown operations for node %s', node.uuid)

            self.simple_node_power_reset(task)                
            #manager_utils.node_power_action(task, states.REBOOT)
            LOG.info('stop_console for node %s', node.uuid)
            
            #task.driver.console.stop_console(task)     
            LOG.info('Successfully completed REBOOT for node %s', node.uuid)

            return states.DELETED
        
        else:
          raise exception.InstanceDeployFailure(_("Node %(node_uuid)s lacks the capability for dpu_boot.") %
                                                {'node_uuid': node.uuid})
        
    @METRICS.timer('DpuDeploy.prepare')
    def prepare(self, task):
        pass   #need to do

    @METRICS.timer('DpuDeploy.clean_up')
    def clean_up(self, task):
        LOG.info("Starting clean_up for task %s", task.node.uuid)
        deploy_utils.destroy_images(task.node.uuid)
        task.driver.boot.clean_up_ramdisk(task)
        task.driver.boot.clean_up_instance(task)
        provider = dhcp_factory.DHCPFactory()
        provider.clean_dhcp(task)

    @METRICS.timer('DpuDeploy.take_over')
    def take_over(self, task):
        pass   #nothing to do

    @METRICS.timer('DpuDeploy.prepare_cleaning')
    def prepare_cleaning(self, task):
        LOG.info("Starting prepare_cleaning for task %s", task.node.uuid)
        return deploy_utils.prepare_inband_cleaning(task, manage_boot=True)
    
    @METRICS.timer('DpuDeploy.tear_down_cleaning')        
    def tear_down_cleaning(self, task):
        LOG.info("Starting tear_down_cleaning for task %s", task.node.uuid)
        deploy_utils.tear_down_inband_cleaning(task, manage_boot=True)

