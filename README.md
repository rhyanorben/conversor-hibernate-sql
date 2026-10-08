# Hibernate → PostgreSQL

Aplicação local em Python 3.8+ com interface no navegador. Usa apenas a biblioteca padrão do Python; não precisa de pip nem de acesso ao banco.

## Executar

Na raiz do projeto:

```sh
python3 ferramentas/hibernate-sql/app.py
```

O navegador abre em http://127.0.0.1:8765. Para abrir manualmente ou usar outra porta:

```sh
python3 ferramentas/hibernate-sql/app.py --no-browser --port 8766
```

Cole os logs com a SQL e todas as linhas `binding parameter (posição:TIPO) <- [valor]`. Clique em **Montar query**, ou escolha **EXPLAIN ANALYZE** e clique em **Montar com comando**. Use **Copiar SQL** para levar o resultado ao PostgreSQL. Encerre o servidor com Ctrl+C.

## Adicionar comandos

Edite o dicionário `PREFIXES` em `app.py` e reinicie a aplicação. A chave é o nome exibido na seleção e o valor é o comando inserido antes de cada SQL:

```python
PREFIXES = {
    'EXPLAIN ANALYZE': 'EXPLAIN ANALYZE',
    'EXPLAIN': 'EXPLAIN',
    'EXPLAIN com buffers': 'EXPLAIN (ANALYZE, BUFFERS)',
}
```

## Comportamento

- Reconhece `org.hibernate.SQL :` e `Hibernate:` e remove a duplicação consecutiva da mesma SQL sem binds entre elas.
- Substitui parâmetros pela posição, incluindo posições maiores que 9 e binds fora de ordem.
- Trata números, booleanos, NULL, textos com aspas/barras, datas, horários e UUIDs. Outros tipos são representados como texto SQL.
- Preserva interrogações dentro de strings, identificadores e comentários SQL.
- Aceita SQL em várias linhas e vários blocos consecutivos de SQL/binds. Cole blocos de uma execução por vez: logs intercalados de threads diferentes precisam ser separados antes da conversão.
- Recusa parâmetros ausentes, excedentes ou repetidos. `?` usado como operador PostgreSQL fora de strings é interpretado como placeholder.
- Usa o texto visível no log: valores truncados, binários, arrays e objetos que exigem serialização própria não podem ser reconstruídos de forma confiável. Um texto literal `null` não pode ser distinguido de NULL nesse formato de log.

Os logs são processados localmente, não são gravados e nenhuma query é executada pela aplicação. Ao executar `EXPLAIN ANALYZE` no PostgreSQL, o banco executa a instrução, inclusive INSERT/UPDATE/DELETE.

## Verificar

```sh
cd ferramentas/hibernate-sql
python3 -m unittest -v
```
