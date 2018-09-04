Limes integration
=================

[Limes](https://github.com/sapcc/limes) currently reports resource quota and usage for a project as described [here](https://github.com/sapcc/limes/blob/master/docs/users/api-v1-specification.md#get-v1domainsdomain_idprojectsproject_id).
Add rate limits by extending the JSON document as follows.

Example:  
**GET /v1/domains/:domain_id/projects/:project_id**
```
{
    "projects": [
        {
            "id": <project_id>,
            ...
            "services": [
                {
                    "type": "object-store",
                    "area": "storage",
                    "resources": [
                        {
                        ...
                        }
                    ],
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

**Defaults** for each project will be deployed using limes' constraints.

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

