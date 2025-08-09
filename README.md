# NBBM Bare Metal Architecture
The NBBM bare-metal architecture primarily consists of a control node, multiple bare-metal nodes, and several dedicated storage nodes. Each bare metal node is equipped with a SmartNIC(DPU), which enables remote connection to the storage nodes for data access and storage functions. The installation position of the SmartNIC is shown in the diagram below, located inside each bare-metal node. 

<div align="center">
  <img src="./images/smartnic-installation.png" alt="SmartNIC Installation" width="500">
</div>

## Code Repositories

The relevant code is organized as follows:

- The code running on the OpenStack control node is available at:  
  [https://github.com/baremetal-njupt/NBBM.git](https://github.com/baremetal-njupt/NBBM.git)

- The code running on the SmartNIC is available at:  
  [https://github.com/baremetal-njupt/smartnic-agent.git](https://github.com/baremetal-njupt/smartnic-agent.git)

- The code implementing the SmartNIC-based forwarding logic for bare-metal traffic is available at:  
  [https://github.com/baremetal-njupt/smartnic-forwarding.git](https://github.com/baremetal-njupt/smartnic-forwarding.git)

# Quick Start

This project is based on the OpenStack Yoga release and extends the functionality of the Ironic component to support the management and control of SmartNIC devices. Leveraging the unique design of the NBBM architecture, traditional standalone compute nodes are no longer essential, as relevant compute components can be directly integrated into the control node. Alternatively, the compute node structure may be retained to facilitate hierarchical control over downstream SmartNICs in multi-level management systems. The project provides deployable Ironic-Conductor component code, which can be installed on the control node. For existing cloud platforms, the original Ironic-Conductor component on compute nodes can be directly replaced to enable enhanced management capabilities for SmartNICs.


## Installation of the OpenStack-side module

### Install
You can follow the instrucitons below to quickly install Ironic-Conductor component.

- Use the following command to clone the project:
```bash
git clone https://github.com/baremetal-njupt/NBBM.git
```

- Enter the project directory
```bash
cd ../../NBBM-main
```
- Install the new Ironic-Conductor code
```bash
python3 setup.py install
```

- Run Ironic-Conductor
```bash
python3 -m ironic.cmd.conductor &
```

### Setup

You can follow the instrucitons below to quickly set up the environtments.

- Open the ironic configuration file
Use a text editor such as vi to open the Ironic configuration file:
```bash
$ vi /etc/ironic/ironic.conf
```
- Modify or verify the following ironic configuration options：

```bash
[DEFAULT]
enabled_hardware_types = dpu_ipmitool
enabled_boot_interfaces = dpu-boot
enabled_deploy_interfaces = dpu-deploy,direct
default_deploy_interface = dpu-deploy
enabled_storage_interfaces = dpu-storage,cinder,noop
default_storage_interface = dpu-storage
enabled_inspect_interfaces = no-inspect

[conductor]
sync_power_state_interval = 0
automated_clean = false

[inspector]
enabled = false
```
> 💡 After completing the configuration, restart the ironic-conductor service to apply the changes.


- Use a text editor such as vi to open the nova-compute configuration file:
```bash
$ vi .../.../nova-compute.conf
```

- Modify or verify the following nova-compute configuration options：
```bash
[DEFAULT]
compute_driver = ironic.IronicDriver
```
> 💡This configuration only affects the current node. Alternatively, you can modify the global nova.conf for all nodes.

- Restart required Nova services
```bash
systemctl restart nova-compute
systemctl restart nova-api
systemctl restart nova-scheduler
systemctl restart nova-conductor
systemctl restart httpd
```

## Install the SmartNIC-side module 
The SmartNIC code and installation guide are available at:
https://github.com/baremetal-njupt/smartnic-agent.git


## Install Network functionality (Optional)
The code and installation guide are available at:
https://github.com/baremetal-njupt/smartnic-forwarding.git
> 💡 If forwarding host traffic via the SmartNIC is not required and only fast boot is desired, this step can be skipped.

# Command Usage Steps

### 1. List available bare-metal drivers
```bash
openstack baremetal driver list
```
Lists all registered bare-metal drivers; dpu_ipmitool should appear here.


### 2. Start the Ironic Python Agent on the SmartNIC(execute on the SmartNIC)
```bash
ironic-python-agent --config-file ipa.conf
```
Launches the Ironic Python Agent (IPA) with the specified configuration file to manage and configure the bare-metal node.
> 💡 The agent runs as a persistent service and can be enabled to start automatically on SmartNIC(DPU) boot, so this step only needs to be performed once.

### 3. Register a bare-metal node
```bash
openstack baremetal node create \
  --name <NODE_NAME> \
  --driver dpu_ipmitool \
  --driver-info ipmi_address=<IPMI_ADDR> \
  --driver-info ipmi_username=<USERNAME> \
  --driver-info ipmi_password=<PASSWORD> \
  --property capabilities='dpu_boot:True' \
  --resource-class HIGH_PERFORMANCE \
  --extra dpu='{"ip_addr": "<DPU_IP>"}'
```
Creates a new node named <NODE_NAME> using the dpu_ipmitool driver, with IPMI credentials, DPU-boot capability, resource class, and the SmartNic’s management IP.
> 💡 `--resource-class HIGH_PERFORMANCE` assigns the node to the `HIGH_PERFORMANCE` resource class. Ensure this class is created beforehand (e.g. via `openstack resource class create CUSTOM_HIGH_PERFORMANCE`; omit the `CUSTOM_` prefix when registering the node).


### 4. Create a bare-metal port
 ```bash
openstack baremetal port create \
  --node <NODE_UUID> \
  <MAC_ADDRESS>
```
Registers a network port for the node identified by <NODE_UUID>, using the virtio-net MAC address from the SmartNIC(DPU).

### 5. Create an iSCSI-IP volume connector
```bash
openstack baremetal volume connector create \
  --node <NODE_UUID> \
  --type ip \
  --connector-id <TARGET_IP>
```
Adds an IP-type volume connector so the node can discover and attach iSCSI volumes via <TARGET_IP>. Here, <TARGET_IP> is the IP address of the storage node.

### 6. Create an iSCSI-IQN volume connector
```bash
openstack baremetal volume connector create \
  --node <NODE_UUID> \
  --type iqn \
  --connector-id <TARGET_IQN>
```
Adds an IQN-type volume connector so the node can discover and attach iSCSI volumes via <TARGET_IQN>. Here, <TARGET_IQN> specifies the iSCSI Qualified Name of the target storage volume.

### 7. Create a boot volume target
```bash
openstack baremetal volume target create \
  --node <NODE_UUID> \
  --type dpu \
  --boot-index 0 \
  --volume <VOLUME_ID>
```
Defines which volume (<VOLUME_ID>) the node should boot from (boot index 0). 
> 💡 This boot target is consumed after a successful boot and must be recreated for subsequent boots. 

### 8. Manage and provide the node
```bash
openstack baremetal node manage  <NODE_UUID>
openstack baremetal node provide <NODE_UUID>
```
manage: Marks the node “manageable.”
provide: Marks the node “available” for deployment.

### 9. Set the resource provider inventory
```bash
openstack resource provider inventory set <NODE_UUID> \
  --resource VCPU=16 \
  --resource MEMORY_MB=32768 \
  --resource DISK_GB=500 \
  --resource CUSTOM_HIGH_PERFORMANCE=10
```
Configures the node’s available resources (CPU, memory, disk, and custom performance units). Adjust these values to match the node’s actual hardware specifications.

### 10. Create a bare-metal server
```bash
openstack server create \
  --flavor HighPerformance \
  --image <IMAGE_ID> \
  --network <NETWORK_ID> \
  <SERVER_NAME>
```
Deploys an instance on the target node using the specified flavor (bound to CUSTOM_HIGH_PERFORMANCE), image, and network. If creation fails, re-run step 3.9 and retry.
> 💡 The --image and --network options can reference any existing image and network IDs in your environment to satisfy the command syntax.

flavor HighPerformance specifies the bare-metal instance flavor, i.e. the resource allocation profile. In this example, it uses a flavor named HighPerformance, which must be created in advance and bound to the CUSTOM_HIGH_PERFORMANCE resource class. For instance:
```bash
openstack flavor create \
  --id auto \
  --ram 1026 \
  --disk 10 \
  --vcpus 4 \
  --property resources:CUSTOM_HIGH_PERFORMANCE='1' \
  HighPerformance
```

### 11. Bind the Neutron port to the SmartNIC(DPU) (Optional)
```bash
openstack port set \
  --vnic-type remote-managed \
  --binding-profile '{
    "pci_vendor_info":"1",
    "pci_slot":"1",
    "physical_network":"11",
    "card_serial_number":"<CARD_SN>",
    "pf_mac_address":"<MAC_ADDRESS>",
    "vf_num":-1
  }' \
  <NEUTRON_PORT_ID>
```
Configures the Neutron port so that OVN-generated flow rules are offloaded to the SmartNIC’s virtio-net interface.

### 12. Configure the server’s IP on the host (Optional)
```bash
ip addr add <IP_ADDR>/<PREFIX> dev <IF_NAME>
ip link set dev <IF_NAME> up
```
Assigns and activates the IP address for the host interface (<IF_NAME>, e.g. ens1), matching the MAC used in step 3.4.

### 13. Delete the bare-metal server
```bash
openstack server delete <SERVER_NAME>
```
Removes the instance named <SERVER_NAME>, freeing its compute and storage resources. If the SmartNIC(DPU) is busy, retry the command.

### 14. Re-deploy from a specific volume
If the node has already booted once and you wish to boot again from a particular volume without deleting it, repeat step 7 "create the boot volume target" and all subsequent steps.


# Extended Functionality
All commands are pre-integrated. To add custom instructions for the SmartNIC(DPU), define them in ironic/drivers/modules/storage/dpu_storage.py and trigger them at the appropriate point in the deployment workflow—such as within a specific step in ironic/drivers/modules/dpu_deploy.py.
