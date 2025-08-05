from oslo_config import cfg
from oslo_log import log
from oslo_utils import excutils
from oslo_utils import strutils
import retrying

from ironic.common import cinder
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import states
from ironic.drivers import base
from ironic.drivers import utils
from ironic import objects

LOG = log.getLogger(__name__)

from ironic.conductor import task_manager
import requests

VALID_DPU_TYPES = ('iqn',)

class DpuStorage(base.StorageInterface):
    """A storage_interface driver supporting DPU."""

    def get_properties(self):
        return {}

    def _fail_validation(self, task, reason,
                         exception=exception.InvalidParameterValue):
        msg = (_("Failed to validate DPU storage interface for node "
                 "%(node)s. %(reason)s") %
               {'node': task.node.uuid, 'reason': reason})
        LOG.error(msg)
        raise exception(msg)

    def _validate_connectors(self, task):
        node = task.node
        dpu_uuids_found = []
    
        for connector in task.volume_connectors:
            if (connector.type in VALID_DPU_TYPES
                    and connector.connector_id is not None):
                dpu_uuids_found.append(connector.uuid)
    
        if len(dpu_uuids_found) > 1:
            LOG.warning("Multiple possible DPU connectors, "
                        "%(dpu_uuids_found)s found, for node %(node)s. "
                        "Only the first DPU connector, %(dpu_uuid)s, "
                        "will be utilized.",
                        {'node': node.uuid,
                         'dpu_uuids_found': dpu_uuids_found,
                         'dpu_uuid': dpu_uuids_found[0]})
        return {'dpu_found': len(dpu_uuids_found) >= 1}


    def _validate_targets(self, task, found_types, dpu_boot):
        for volume in task.volume_targets:
            if volume.volume_id is None:
                msg = (_("volume_id missing from target %(id)s.") %
                       {'id': volume.uuid})
                self._fail_validation(task, msg)
    
            elif volume.volume_type == 'DPU':
                if not dpu_boot and volume.boot_index == 0:
                    msg = (_("Volume target %(id)s is configured for "
                             "'DPU', however the capability 'dpu_boot' "
                             "is not set for the node.") %
                           {'id': volume.uuid})
                    self._fail_validation(task, msg)
                if not found_types['dpu_found']:
                    msg = (_("Volume target %(id)s is configured for "
                             "'DPU', however no DPU connectors are "
                             "configured for the node.") %
                           {'id': volume.uuid})
                    self._fail_validation(task, msg)
            else:
                msg = (_("Volume target %(id)s is of an unknown type "
                         "'%(type)s'. Supported types: 'DPU'") %
                       {'id': volume.uuid, 'type': volume.volume_type})
                self._fail_validation(task, msg)


    def validate(self, task):
        found_types = self._validate_connectors(task)
        node = task.node
        dpu_boot = strutils.bool_from_string(
            utils.get_node_capability(node, 'dpu_boot'))

        if dpu_boot and not found_types['dpu_found']:
            valid_types = ', '.join(VALID_DPU_TYPES)
            msg = (_("In order to enable the 'dpu_boot' capability for "
                     "the node, an associated volume_connector type "
                     "must be valid for DPU (%(options)s).") %
                   {'options': valid_types})
            self._fail_validation(task, msg)

        self._validate_targets(task, found_types, dpu_boot)
        
    def _connect(self, task, data):


        ip = data['ip']
        iqn = data['initiator'] 
        
        print("#################################hello word! This is dpu_ipmitool driver!################################################################")
        print("===IN===:", iqn)
        print("===IP===:", ip)
        
        #ipmi_address = task.driver_info.get('ipmi_address')

        node = task.node
        
        dpu_ipaddr = node.extra.get('dpu').get('ip_addr')
        
        LOG.info("connect to dpu : DPU IP is : %s", dpu_ipaddr)
        
        #ipmi_address = "192.168.3.18"

        ipa_url = f"http://{dpu_ipaddr}:9999/v1/commands/"
   
 
        
        command_data = {
            "name": "cloud_disk.connect_cloud_disk",
            "params": {
                "iqn": iqn,   
                "ip": ip  
            }
        }
              
        try:
            response = requests.post(ipa_url, json=command_data)
            response_data = response.json()

            if response.status_code != 200:
                raise Exception(f"Error from IPA: {response_data.get('message', '')}")     
            connection_status = response_data.get('result')
            LOG.info("Cloud disk connection status: %s", connection_status)
            
        except requests.RequestException as exc:
            LOG.error("Failed to send command to IPA: %s", exc)
            raise        
    
    def _attach_volumes(self, task, volume_list, connector):
        """
        ...[unchanged docstring]...
        """
        node = task.node
    
        connected = []
        for volume_id in volume_list:
            try:
                # Directly use _connect without checking attachment status.
                self._connect(task, connector)
            except Exception as e:
                msg = (_('Failed to connect volume %(vol_id)s for node %(node)s: '
                         '%(err)s)') %
                       {'vol_id': volume_id, 'node': node.uuid, 'err': e})
                LOG.error(msg)
                raise exception.StorageError(msg)
    
            connection = {'data': {'ironic_volume_uuid': volume_id}}
            connected.append(connection)
    
            LOG.info('Successfully initialized volume %(vol_id)s for '
                     'node %(node)s.', {'vol_id': volume_id, 'node': node.uuid})
    
        return connected


    def attach_volumes(self, task):
        """Informs CustomStorage to attach all volumes for the node.

        :param task: The task object.
        :raises: StorageError If an underlying exception or failure is detected.
        """
        node = task.node
        targets = [target.volume_id for target in task.volume_targets]

        if not targets:
            return

        connector = self._generate_connector(task)
        try:
            connected = self._attach_volumes(task, targets, connector)
        except exception.StorageError as e:
            with excutils.save_and_reraise_exception():
                LOG.error("Error attaching volumes for node %(node)s: "
                          "%(err)s", {'node': node.uuid, 'err': e})
                self.detach_volumes(task, connector=connector,
                                    aborting_attach=True)

        if len(targets) != len(connected):
            LOG.error("The number of volumes defined for node %(node)s does "
                      "not match the number of attached volumes. Attempting "
                      "detach and abort operation.", {'node': node.uuid})
            self.detach_volumes(task, connector=connector,
                                aborting_attach=True)
            raise exception.StorageError(("Mismatch between the number of "
                                          "configured volume targets for "
                                          "node %(uuid)s and the number of "
                                          "completed attachments.") %
                                         {'uuid': node.uuid})

        for volume in connected:
            #if not volume.get('already_attached'):
            volume_uuid = volume['data']['ironic_volume_uuid']
            targets = objects.VolumeTarget.list_by_volume_id(task.context,
                                                             volume_uuid)

            for target in targets:
                target.properties = volume['data']
                target.save()
                
        return connected

    def _disconnect(self, task, data):
        
        ip = data['ip']
        iqn = data['initiator']

        node = task.node
        
        dpu_ipaddr = node.extra.get('dpu').get('ip_addr')
        LOG.info("disconnect to dpu : DPU IP is : %s", dpu_ipaddr)
        
        # Assuming the same base URL structure for disconnecting
        ipa_url = f"http://{dpu_ipaddr}:9999/v1/commands/"
    
        # Changed the command name to 'disconnect_cloud_disk'
        command_data = {
            "name": "cloud_disk.disconnect_cloud_disk",
            "params": {
                "iqn": iqn,
                "ip": ip
            }
        }
    
        try:
            response = requests.post(ipa_url, json=command_data)
            response_data = response.json()
    
            if response.status_code != 200:
                raise Exception(f"Error from IPA: {response_data.get('message', '')}")
    
            disconnection_status = response_data.get('result')
            LOG.info("Cloud disk disconnection status: %s", disconnection_status)
            
        except requests.RequestException as exc:
            LOG.error("Failed to send command to IPA: %s", exc)

    def _detach_volumes(self, task, volume_list, connector, allow_errors):
    
            node = task.node        
       
            for volume_id in volume_list:
                try:
                    # Directly use _disconnect 
                    self._disconnect(task, connector)
                except Exception as e:
                    msg = (_('Failed to disconnect volume %(vol_id)s for node %(node)s: '
                             '%(err)s)') %
                           {'vol_id': volume_id, 'node': node.uuid, 'err': e})
                    LOG.error(msg)
                    raise exception.StorageError(msg)
        
                LOG.info('Successfully detach volume %(vol_id)s for '
                         'node %(node)s.', {'vol_id': volume_id, 'node': node.uuid})        


    def detach_volumes(self, task, connector=None, aborting_attach=False):
        node = task.node
        targets = [target.volume_id for target in task.volume_targets]

        if not targets:
            return

        if not connector:
            connector = self._generate_connector(task)

        @retrying.retry(
            retry_on_exception=lambda e: isinstance(e, exception.StorageError),
            #stop_max_attempt_number=CONF.cinder.action_retries + 1,
            #wait_fixed=CONF.cinder.action_retry_interval * 1000)
            stop_max_attempt_number=3 + 1,
            wait_fixed=5 * 1000)
        def detach_volumes():
            try:
                allow_errors = (task.node.provision_state == states.ACTIVE
                                or aborting_attach and outer_args['attempt'] > 0)
                self._detach_volumes(task, targets, connector,
                                      allow_errors=allow_errors)
            except exception.StorageError as e:
                with excutils.save_and_reraise_exception():
                    if aborting_attach:
                        msg_format = ("Error on aborting volume detach for "
                                      "node %(node)s: %(err)s.")
                    else:
                        msg_format = ("Error detaching volume for "
                                      "node %(node)s: %(err)s.")
                    msg = (msg_format) % {'node': node.uuid, 'err': e}
                    #if outer_args['attempt'] < CONF.cinder.action_retries:
                    if outer_args['attempt'] < 3:
                        outer_args['attempt'] += 1
                        msg += " Re-attempting detachment."
                        LOG.warning(msg)
                    else:
                        LOG.error(msg)

        outer_args = {'attempt': 0}
        detach_volumes()

    def should_write_image(self, task):
        instance_info = task.node.instance_info
        if 'image_source' not in instance_info:
            for volume in task.volume_targets:
                if volume['boot_index'] == 0:
                    return False
        return True

    def _generate_connector(self, task):
        data = {}
        valid = False
        for connector in task.volume_connectors:
            if 'iqn' in connector.type and 'initiator' not in data:
                data['initiator'] = connector.connector_id
                valid = True
            elif 'ip' in connector.type and 'ip' not in data:
                data['ip'] = connector.connector_id
            else:
                LOG.warning('Node %(node)s has a volume_connector (%(uuid)s) '
                            'defined with an unsupported type: %(type)s.',
                            {'node': task.node.uuid,
                             'uuid': connector.uuid,
                             'type': connector.type})
        if not valid:
            valid_types = ', '.join(VALID_DPU_TYPES)
            msg = (_('Insufficient or incompatible volume connection '
                     'records for node %(uuid)s. Valid connector '
                     'types: %(types)s') %
                   {'uuid': task.node.uuid, 'types': valid_types})
            LOG.error(msg)
            raise exception.StorageError(msg)

        data['host'] = task.node.uuid
        if len(task.volume_connectors) > 1 and len(data) > 1:
            data['multipath'] = True

        return data

    def check_heartbeat(self, ip_address):
        """always returning true.
    
        :param ip_address: The IP address of the target device (in your case, DPU).
        :returns: True, indicating successful heartbeat verification.
        """
        
        LOG.info("check_heartbeat to dpu : DPU IP is : %s", ip_address)
        
        # Assuming the same base URL structure for disconnecting
        ipa_url = f"http://{ip_address}:9999/v1/commands/"
    
        # Changed the command name to 'disconnect_cloud_disk'
        command_data = {
            "name": "cloud_disk.check_heartbeat",
            "params": {
                "ip": ip_address
            }
        }
    
        try:
            response = requests.post(ipa_url, json=command_data)
            #response_data = response.json()
    
            if response.status_code != 200:
                raise Exception(f"Error from IPA: {response_data.get('message', '')}")
    
            LOG.info("Received heartbeat from IPA")
            
        except requests.RequestException as exc:
            LOG.error("Failed to send command to IPA: %s", exc)
            raise 
            
        return True

