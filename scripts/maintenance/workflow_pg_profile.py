"""两个已批准PG消费者的不可变运行身份；不授予任意任务执行权限。"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Profile:
    task: str
    run: str
    project: str
    private: str
    port_base: int

    @property
    def ports(self):
        return {name:self.port_base+index for index,name in enumerate(('api','web','idp','platform','source','fuseki','s3','secondary'),1)}

    @property
    def resources(self):
        """已批准PG运行配方的非秘密配额；测试与第二API使用互斥槽位。"""
        values = {'platform-pg': (768, .75), 'pg-source': (768, .75),
                  'keycloak-test': (1024, .5), 'fuseki': (1536, .75),
                  'rustfs': (512, .25), 'api': (768, .75),
                  'api-secondary': (768, .75), 'persistence-test': (768, .5),
                  'maf-test': (768, 2 if self.task == 'G4-M5-INTEGRATION-001' else .5)}
        return {name: dict(memory=memory*1024**2, cpu=int(cpu*1e9))
                for name, (memory, cpu) in values.items()}

    def text(self, value):
        """仅重绑定既有配方中的实例身份/端口，源代码和公开产品合同不替换。"""
        if self.task == 'G4-M4-QUERY-001':return value
        for old,new in [('ontology-g4-m4-query-impl-01',self.project),('g4-m4-query-001',self.private),
                        ('G4-M4-QUERY-001',self.task),('query-impl-01',self.run),('review-fix-01',self.run),
                        ('g4-m4-query-synthetic','g4-m5-integration-synthetic')]:
            value=value.replace(old,new)
        for i in range(1,9):value=value.replace(str(15440+i),str(self.port_base+i))
        return value


def profile(task):
    if task=='G4-M4-QUERY-001':return Profile(task,'query-impl-01','ontology-g4-m4-query-impl-01','g4-m4-query-001',15440)
    if task=='G4-M5-INTEGRATION-001':return Profile(task,'integration-01','ontology-g4-m5-integration-01','g4-m5-integration-001',15540)
    raise ValueError('PG_TASK_NOT_ADMITTED')
