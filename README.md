# notflixbot

*IDEA:* add commands to run key syncs 

*IDEA:* handle olm error, when unknown users

from pushmatrix:

```python
    if newClient.should_upload_keys:
        await newClient.keys_upload()

    if newClient.should_query_keys:
        await newClient.keys_query()

    if newClient.should_claim_keys:
        await newClient.keys_claim()

    await newClient.sync(full_state=True)

```



## libolm

```shell
apt-get install libolm-dev
```
