# Pulumi approach
## Create Pulumi Conda environment on local machine:
``` yaml
name: pulumi
channels:
  - conda-forge
  - nodefaults
dependencies:
  - pulumi-sdk-python
  - pip
  - pip:
    - pulumi
    - pulumi_aws
    - pulumi_tls
```
``` bash
conda env create -f pulumi_env.yml
```
## cd into pulumi directory and launch the machine
```
conda activate pulumi
cd pulumi
pulumi up
```
This should produce outputs like:
```
Outputs:
  + ipfs_gateway_url   : "http://52.42.117.40:8080/ipfs/"
  + ipfs_key_pair_name : "ipfs-node-pulumi-key"
  + ipfs_node_public_ip: "52.42.117.40"
  + private_key        : [secret]
```
Get SSH key:
```
pulumi stack output --show-secrets private_key > ~/.ssh/ipfs-node-pulumi-key.pem
```
SSH in:
```
ssh -i ~/.ssh/ipfs-node-pulumi-key.pem ubuntu@ec2-52-42-117-40.us-west-2.compute.amazonaws.com
```
