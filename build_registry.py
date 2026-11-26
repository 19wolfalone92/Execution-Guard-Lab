import json,csv
from lab import TOOLS
from test_extended import CASES
from pathlib import Path
GROUPS={
 'Исходные':['text_sha256','evidence_bundle_verify','acceptance_evaluate','workflow_validate','test_results_analyze','snapshot_compare','blocker_classify','release_consistency'],
 'Математика':'math_calculate statistics_analyze distribution_analyze correlation_analyze regression_analyze probability_calculate matrix_calculate time_series_analyze numerical_compare calculation_verify'.split(),
 'Верификация':'evidence_verify evidence_compare acceptance_validate acceptance_matrix completion_verify claim_validate regression_detect test_results_analyze release_consistency verification_report'.split(),
 'Код':'code_structure_analyze code_complexity_analyze code_duplicates_detect code_dependencies_analyze code_diff_analyze patch_validate configuration_validate test_coverage_analyze code_regression_detect architecture_consistency_check'.split(),
 'Диагностика':'error_classify error_history_analyze error_pattern_detect root_cause_analyze dependency_check resource_check permission_check retry_evaluate recovery_plan blocker_report'.split(),
 'Артефакты':'artifact_inspect artifact_checksum archive_validate manifest_validate file_type_detect file_integrity_check artifact_compare document_structure_analyze dataset_validate artifact_provenance_verify'.split(),
 'Проекты':'project_snapshot snapshot_compare project_rules_validate project_conflict_detect context_reconstruct context_compact project_progress project_dependencies_analyze project_readiness project_next_action'.split(),
 'Workflow':'workflow_validate workflow_integrity workflow_bottleneck workflow_readiness workflow_stall_detect workflow_next_action workflow_result_compare workflow_dependencies_analyze task_priority_analyze task_completion_evaluate'.split(),
 'Специализация':['equity_drawdown_analyze','exam_results_compare']}
ALIAS={
 'calculation_verify':('numerical_compare','Сравнение с отдельно вычисленным эталоном; не новый универсальный вычислитель.'),
 'evidence_verify':('evidence_bundle_verify','Сверка предоставленных хешей; независимое происхождение требует доверенного источника.'),
 'evidence_compare':('snapshot_compare','Сравнение метаданных/хешей, не истинности.'),
 'acceptance_validate':('acceptance_evaluate + completion_verify','Декларации, хеши, полнота обязательных ID.'),
 'acceptance_matrix':('completion_verify + acceptance_evaluate','Отдельный интерфейс не нужен до новых требований.'),
 'verification_report':('acceptance_evaluate + completion_verify','Отчет по предоставленным данным, не новые доказательства.'),
 'code_complexity_analyze':('code_structure_analyze','Частично: число ветвлений; не цикломатическая сложность.'),
 'code_dependencies_analyze':('code_structure_analyze','Частично: корни Python imports; не разрешение зависимостей.'),
 'code_regression_detect':('regression_detect','Частично: статусы тестов, не семантический diff.'),
 'error_classify':('blocker_classify','Классификация заданных кодов; не произвольный текст.'),
 'retry_evaluate':('blocker_classify','Частично: рекомендация без исполнения; политика всегда stop.'),
 'blocker_report':('blocker_classify','Класс и рекомендация; отдельный отчет не нужен.'),
 'file_integrity_check':('artifact_checksum','Сравнение байтов с ожидаемым SHA-256.'),
 'artifact_compare':('artifact_checksum + snapshot_compare','Сравнение идентификаторов и хешей; не бинарный diff.'),
 'project_snapshot':('Pro project_get / checkpoint_get','Уже предусмотрено Pro; не дублировать постоянное хранилище.'),
 'context_reconstruct':('Pro project_resume','Требует подтвержденного состояния и сверки; не дублировать Pro.'),
 'project_progress':('Pro project_get + workflow_status','Уже предусмотрено Pro; не читать состояние из лаборатории.'),
 'project_dependencies_analyze':('workflow_validate','Частично: явный DAG, не автоматический поиск межпроектных связей.'),
 'project_readiness':('completion_verify','Частично: предоставленные критерии и статусы.'),
 'project_next_action':('workflow_readiness + blocker_classify','Частично: кандидаты из переданного DAG; не выполняет действие.'),
 'workflow_integrity':('workflow_validate / Pro execution_finalize','Граф локально, durable integrity в Pro.'),
 'workflow_next_action':('workflow_readiness','Готовые шаги по входному графу, без запуска.'),
 'workflow_result_compare':('snapshot_compare + regression_detect','Сравнение переданных записей и результатов.'),
 'workflow_dependencies_analyze':('workflow_validate / Pro workflow_dependencies_get','Граф проверяется без отдельного инструмента.'),
 'task_completion_evaluate':('completion_verify','Полнота заявленных критериев.'),
 'dependency_check':('workflow_validate','Частично: явные зависимости, не проверка среды.'),
 }
DEFER={
 'distribution_analyze':'Нужно определить интервалы, веса, квантильный метод и эталоны.',
 'probability_calculate':'Нужна явно определенная вероятностная модель; не универсальная оценка шансов.',
 'matrix_calculate':'Нужны конкретные операции, размеры и численные пределы.',
 'claim_validate':'Истинность утверждения требует независимого доверенного источника; локальный хеш недостаточен.',
 'code_duplicates_detect':'Нужны правила нормализации, метрика сходства и корпус.',
 'code_diff_analyze':'Нужны точные форматы, границы объема и тестовые эталоны.',
 'patch_validate':'Нужна базовая версия и проверка применимости без публикации или выполнения.',
 'configuration_validate':'Нужна версия конкретной схемы; универсальный валидатор не нужен.',
 'test_coverage_analyze':'Нужны coverage-отчеты и соответствующая версия исходников.',
 'architecture_consistency_check':'Нужны формализованные архитектурные ограничения проекта.',
 'error_history_analyze':'Нужны обезличенные записи событий и структура времени.',
 'error_pattern_detect':'Нужен репрезентативный набор ошибок и пороги совпадения.',
 'root_cause_analyze':'Причина не выводится достоверно из одного сообщения; нужны наблюдения и контрольные тесты.',
 'resource_check':'Реальные метрики требуют отдельно разрешенного источника, не произвольного доступа к устройству.',
 'permission_check':'Проверка прав требует источника с официальной авторизацией; аннотации не доказательство.',
 'recovery_plan':'Контекстная рекомендация без автоматического выполнения; нужна формализованная модель ошибок.',
 'artifact_inspect':'Разные форматы требуют специализированных безопасных анализаторов.',
 'manifest_validate':'Нужно выбрать формат манифеста, обязательные файлы и доверенный эталон.',
 'file_type_detect':'Magic bytes не устанавливают безопасность или тип сложного полиглот-файла.',
 'document_structure_analyze':'Нужны отдельные парсеры PDF/DOCX с лимитами и защитой от внедренных инструкций.',
 'artifact_provenance_verify':'Нужны доверенные подписи/attestations и цепочка доверия; хеш недостаточен.',
 'project_rules_validate':'Нужен машинно-проверяемый набор правил; свободный текст не исполняется.',
 'project_conflict_detect':'Нужны версии и записи активных владельцев; источник должен быть авторизован.',
 'context_compact':'Нужны правила сохранения фактов и проверка потерь; текст не должен содержать секреты.',
 'workflow_bottleneck':'Нужны временные метрики задач и модель ресурсов.',
 'workflow_stall_detect':'Нужны проверенные timestamps/leases и пороги; Pro уже хранит состояние.',
 'task_priority_analyze':'Нужны формальные приоритеты, зависимости и критерии; не менять очередь.',
 }
registry={n:{'name':n,'description':s['description'],'inputSchema':s['inputSchema'],'outputSchema':s['outputSchema'],'required_permissions':'trusted local caller; no external scopes; remote connector authorization not qualified','data_source':'caller-supplied values only','side_effects':'none by design; local transport writes response only','cost':'local CPU/memory, no external API charges measured; hosting/ChatGPT costs not assessed','automated_tests':'pytest + independent process stdio/HTTP fixtures','highest_level':'L3-local','L4':'UNVERIFIED','L5':'UNVERIFIED','L6':'UNVERIFIED','origin':'legacy improved' if n in GROUPS['Исходные'] else 'new'} for n,(s,f) in TOOLS.items()}
rows=[];seen=set()
for g,names in GROUPS.items():
 for n in names:
  if n in seen:continue
  seen.add(n)
  if n in registry:target=n;state='IMPLEMENTED';why=registry[n]['description'];level='L3-local'
  elif n in ALIAS:target,why=ALIAS[n];state='MERGED_OR_PARTIAL';level='L0'
  else:target='';why=DEFER[n];state='DEFERRED';level='L0'
  rows.append({'group':g,'candidate':n,'state':state,'target':target,'level':level,'reason':why})
assert set(registry)<=seen
Path('TOOL_REGISTRY.json').write_text(json.dumps(list(registry.values()),ensure_ascii=False,indent=2))
with open('CANDIDATE_CATALOG.csv','w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
from collections import Counter
print(len(rows),Counter(r['state'] for r in rows),Counter(r['level'] for r in rows))
