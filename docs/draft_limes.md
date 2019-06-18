Limes integration
=================

Global rate limits and defaults for each project can be defined via a [configuration file](./configure.md).  
However, the configuration file does not allow defining rate limits specific for a project.  
This can only be done using [Limes](https://github.com/sapcc/limes) as outlined below. 
Limes reports rate limits for a project as described [here](https://github.com/sapcc/limes/blob/master/docs/users/api-v1-specification.md#get-v1domainsdomain_idprojectsproject_id).

Note the usage of the `rate=only` query parameter to only report rate limits.

Example:  
**GET /v1/domains/:domain_id/projects/:project_id?rates=only**
```
{
    "projects": [
        {
            "id": <project_id>,
            ...
            "services": [
                {
                    "type": "object-store",
                    "area": "storage"
                    "rates": [
                        {
                            "targetTypeURI": "account/container",
                            "actions": [
                                {
                                    "name": "update",
                                    "limit": "2r/m"
                                },
                                {
                                    "name": "delete",
                                    "limit": "2r/30m"
                                }
                            ]                            
                        }
                    ]
                }
            ]
        }
    ]
}
```

**Defaults** for each project may be deployed using limes' constraints.

```
limes: 
  seeds: 
    ccloud: 
      projects in domain: 
        monsoon3: 
          object-store: 
            rates:
                global: 
                  account/container: 
                    - action: update
                      limit: 2r/m
                    - action: create
                      limit: 5r/30m
                default:
                  account/container: 
                    - action: update
                      limit: 2r/m
                    - action: create
                      limit: 5r/30m   
```

