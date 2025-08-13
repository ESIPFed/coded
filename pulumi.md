# Pulumi approach
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
conda env create -f pulumi_env.yml

Get SSH key:
```
pulumi stack output --show-secrets private_key > ~/.ssh/ipfs-node-pulumi-key.pem
```
