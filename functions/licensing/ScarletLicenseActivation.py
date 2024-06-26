import machineid, pickle, redis,requests, json, os,click,sys
from dotenv import load_dotenv
from pathlib import Path
from hashlib import sha256

"""
Activate license to particular machine

python3 activate_license.py --license_key "" --machine_id ""
"""


class ScarletLicenseActivation:

    def __init__(self):
        if "REDIS_HOST" not in os.environ.keys():
            raise Exception("REDIS_HOST not set in os.environ or manager.env")
        if "REDIS_PORT" not in os.environ.keys():
            raise Exception("REDIS_PORT not set in os.environ or manager.env")
        if "REDIS_AUTH_TOKEN" not in os.environ.keys():
            raise Exception("REDIS_AUTH_TOKEN not set in os.environ or manager.env")
        if "KEYGEN_ADD_ACC_ID" not in os.environ.keys():
            raise Exception("KEYGEN_ADD_ACC_ID not set in os.environ or manager.env")
        if "CACHE_EXPIRE_TIME" not in os.environ.keys():
            raise Exception("CACHE_EXPIRE_TIME not set in os.environ or manager.env")

        self.expireTime = int(os.environ["CACHE_EXPIRE_TIME"])
        self.KEYGEN_ACC_ID = os.environ["KEYGEN_ADD_ACC_ID"]
        self.REDIS_HOST = os.environ["REDIS_HOST"]
        self.REDIS_PORT = os.environ["REDIS_PORT"]
        self.REDIS_PWD = os.environ["REDIS_AUTH_TOKEN"]

    def acquireValidationCache(self,machine_fingerprint,license_key):
        try:

            r = redis.StrictRedis(
                host=self.REDIS_HOST,
                port=int(self.REDIS_PORT),
                password=str(self.REDIS_PWD),
            )

        except Exception as e:
            return False, {
                "error": "Trouble connecting to redis {}:{} with error {}".format(self.REDIS_HOST, self.REDIS_PORT,
                                                                                  str(e))}

        if r.exists(str(machine_fingerprint)+"_validation_record"):
            validation_record_obj = r.get(str(machine_fingerprint + "_validation_record"))
            validation_record = pickle.loads(validation_record_obj)

        else:
            print("ValidationCacheMiss machine_fingerprint {}".format(machine_fingerprint))
            status, response = self.getRemoteValidationRecord(machine_fingerprint, license_key)
            if not status:
                return status, response

            validation_record = response["validation_record"]

        r.set(str(machine_fingerprint)+"_validation_record", pickle.dumps(validation_record), ex=self.expireTime )

        return True, {"validation_record":validation_record}

    def getRemoteValidationRecord(self, machine_fingerprint, license_key):
        try:
            validation = requests.post(
                "https://api.keygen.sh/v1/accounts/{}/licenses/actions/validate-key".format(self.KEYGEN_ACC_ID),
                headers={
                    "Content-Type": "application/vnd.api+json",
                    "Accept": "application/vnd.api+json",
                },
                data=json.dumps(
                    {
                        "meta": {
                            "scope": {"fingerprint": machine_fingerprint},
                            "key": license_key,
                        }
                    }
                ),
            ).json()

        except Exception as e:
            return False, {"error":"Trouble connecting to the Keygen API for validation POST /validate-key"}

        if "errors" in validation:
            errs = validation["errors"]
            err_msg = ",".join(map(lambda e: "{} - {}".format(e["title"], e["detail"]).lower(), errs))
            return False, {"error":"license validation failed: {}".format(err_msg)}

        return True, {"validation_record":validation}


    def validate_key(self,machine_fingerprint,license_key):
        status,response = self.acquireValidationCache(machine_fingerprint,license_key)
        if not status:
            return status, response

        validation = response["validation_record"]
        # try:
        #     validation = requests.post(
        #         "https://api.keygen.sh/v1/accounts/{}/licenses/actions/validate-key".format(self.KEYGEN_ACC_ID),
        #         headers={
        #             "Content-Type": "application/vnd.api+json",
        #             "Accept": "application/vnd.api+json",
        #         },
        #         data=json.dumps(
        #             {
        #                 "meta": {
        #                     "scope": {"fingerprint": machine_fingerprint},
        #                     "key": license_key,
        #                 }
        #             }
        #         ),
        #     ).json()
        #
        # except Exception as e:
        #     return False, {"error":"Trouble connecting to the Keygen API for validation POST /validate-key"}
        #
        # if "errors" in validation:
        #     errs = validation["errors"]
        #     err_msg = ",".join(map(lambda e: "{} - {}".format(e["title"], e["detail"]).lower(), errs))
        #     return False, {"error":"license validation failed: {}".format(err_msg)}

        # If the license is valid for the current machine, that means it has
        # already been activated. We can return early.
        if validation["meta"]["valid"]:
            return True, {"pre_existing_activation": "license has already been activated on this machine"}

        # Otherwise, we need to determine why the current license is not valid,
        # because in our case it may be invalid because another machine has
        # already been activated, or it may be invalid because it doesn't
        # have any activated machines associated with it yet and in that case
        # we'll need to activate one.
        validation_code = validation["meta"]["code"]
        activation_is_required = (
                validation_code == "FINGERPRINT_SCOPE_MISMATCH"
                or validation_code == "NO_MACHINES"
                or validation_code == "NO_MACHINE"
        )

        if not activation_is_required:
            return False, {"license_invalid":"reason : {}, detail: {}".format(validation_code,validation["meta"]["detail"])}

        return True,{"activation_required":validation}

    def keygen_activate(self,machine_fingerprint,license_key,validation,node_ip,app_name,scarlet_name):
        print(license_key)
        try:
            # If we've gotten this far, then our license has not been activated yet,
            # so we should go ahead and activate the current machine.
            activation = requests.post(
                "https://api.keygen.sh/v1/accounts/{}/machines".format(
                    str("34b683d0-6121-4a5a-ac92-ee6320611484")
                ),
                headers={
                    "Authorization": "License {}".format(license_key),
                    "Content-Type": "application/vnd.api+json",
                    "Accept": "application/vnd.api+json",
                },
                data=json.dumps(
                    {
                        "data": {
                            "type": "machines",
                            "attributes": {
                                             "fingerprint": machine_fingerprint,
                                             "ip" : str(node_ip),
                                             "name" : str(app_name),
                                             "metadata" : {
                                                            "scarlet_name":str(scarlet_name)
                                                          }
                                          },
                            "relationships": {
                                "license": {
                                    "data": {
                                        "type": "licenses",
                                        "id": validation["data"]["id"],
                                    }
                                }
                            },
                        }
                    }
                ),
            ).json()
        except Exception as e:
            return False, {"error":"Could not connect to Keygen API to activate license returned with error {}".format(str(e))}

        # If we get back an error, our activation failed.
        if "errors" in activation:
            errs = activation["errors"]
            err_msg = ",".join(map(lambda e: "{} - {}".format(e["title"], e["detail"]).lower(),errs))
            return False, {"error": "license activation failed: {}".format(err_msg)}

        return True, {"success":"license activated"}

    def activate_license(self,scarlet_id,app_name,scarlet_name,node_ip):

        try:
            machine_fingerprint = sha256(str(scarlet_id).encode('utf-8')).hexdigest() #machineid.hashed_id(str(scarlet_id))
        except Exception as e:
            return False, {"error": "Trouble obtaining machine fingerprint for scarlet_id {}, returned with error {}".format(scarlet_id,e)}
        try:

            r = redis.StrictRedis(
                host=self.REDIS_HOST,
                port=int(self.REDIS_PORT),
                password=str(self.REDIS_PWD),
                )

        except Exception as e:
            return False, {"error": "Trouble connecting to redis {}:{} with error {}".format(self.REDIS_HOST,self.REDIS_PORT,str(e))}

        try:
            orig_license_key = r.get(str(node_ip))
        except Exception as e:
            return False, {"error":"Trouble getting license key from redis with error {}".format(e)}

        license_key = orig_license_key.decode()

        status,response = self.validate_key(machine_fingerprint,license_key)
        if not status:
            return status, response
        else:
            if "activation_not_required" in response.keys() or "pre_existing_activation" in response.keys():
                return status, response

        validation = response["activation_required"]

        status, response = self.keygen_activate(machine_fingerprint,license_key,validation,node_ip,app_name,scarlet_name)

        return status, response
