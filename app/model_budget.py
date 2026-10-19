"""One request/deadline budget shared by writing, repair and review."""
import copy,time
from connectors import ConnectorError


class BudgetedModel:
    def __init__(self,client,run,limit=4,seconds=120):
        self.client=client;self.run=run;self.limit=limit;self.deadline=time.monotonic()+seconds
        self.purpose='创作';run['model_calls']=[];run['model_request_limit']=limit

    def __getattr__(self,name):return getattr(self.client,name)

    def chat_json(self,*args,**kwargs):
        calls=self.run['model_calls'];remaining=self.deadline-time.monotonic()
        if len(calls)>=self.limit or remaining<=0:
            raise ConnectorError('本次生成已达到调用或时间上限，已停止自动修订；请根据具体问题调整要求。',kind='request_budget')
        call={'purpose':self.purpose,'messages':copy.deepcopy(args[0])};calls.append(call)
        start=time.monotonic();old_timeout=getattr(self.client,'timeout',None)
        if old_timeout is not None:self.client.timeout=min(old_timeout,remaining)
        try:
            result=self.client.chat_json(*args,**kwargs);call['output']=copy.deepcopy(result)
            completion=getattr(self.client,'last_completion',None)
            if completion:call.update(request_id=completion.request_id,usage=completion.usage)
            return result
        except ConnectorError as error:
            call['failure_kind']=error.kind;raise
        finally:
            call['duration_ms']=round((time.monotonic()-start)*1000)
            if old_timeout is not None:self.client.timeout=old_timeout
