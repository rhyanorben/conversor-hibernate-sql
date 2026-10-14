# Hibernate → PostgreSQL

Aplicação local que reconstrói SQL PostgreSQL a partir dos logs de SQL e binding do Hibernate. O aplicativo usa Python 3.8+ e apenas a biblioteca padrão. Node.js 22+ é necessário somente para os testes do JavaScript. Não há dependências para instalar nem conexão com o banco.

## Executar

Na raiz do projeto:

```sh
python3 app.py
```

O navegador abre em http://127.0.0.1:8765. Para abrir manualmente ou usar outra porta:

```sh
python3 app.py --no-browser --port 8766
```

A porta `0` seleciona uma porta disponível; o endereço efetivo aparece no terminal. Encerre o servidor com Ctrl+C.

Cole os logs com a SQL e todas as linhas `binding parameter (posição:TIPO) <- [valor]`. Clique em **Montar query**, ou escolha **EXPLAIN ANALYZE** e clique em **Montar com comando**. Use **Copiar SQL** para levar o resultado ao PostgreSQL. Se o navegador não permitir acesso à área de transferência, a SQL será selecionada para copiar manualmente.

## Organização e dependências

```text
app.py                            Entrada para execução local
converter.py                      API compatível: convert, literal, substitute
hibernate_sql/
  bootstrap.py                    Composição de objetos e configuração do servidor
  domain/
    models.py                     Query, binding e validação de posições
    literals.py                   Literais PostgreSQL e conversão de tipos
    substitution.py               Substituição de placeholders e leitura de regiões SQL
  application/
    ports.py                      Contrato do leitor de queries
    conversion.py                 Caso de uso, duplicação e formatação do resultado
  infrastructure/
    hibernate_logs.py             Leitura do formato de logs do Hibernate
  presentation/
    http.py                       Rotas, validação HTTP e respostas JSON
    web/
      index.html                  Estrutura da interface
      styles.css                  Apresentação visual
      api.js                      Cliente HTTP
      controller.js               Estado da tela e ações do usuário
      app.js                      Composição da interface no navegador
tests/
  fixtures/multiline-70.log        Exemplo de regressão com 70 parâmetros
  test_*.py                       Testes Python por responsabilidade
  frontend.test.js                Testes da API JavaScript e da interface
tools/check_coverage.py            Medição Python com a biblioteca padrão
```

O domínio é independente das demais camadas. A aplicação depende do domínio e de um contrato de leitura, sem conhecer HTTP nem o formato dos logs. A infraestrutura implementa esse contrato; a apresentação chama o caso de uso. `bootstrap.py` conecta as implementações. O teste de arquitetura verifica essas direções de dependência.

`app.py` e `converter.py` preservam os pontos de entrada existentes. Para usar a conversão em outro programa:

```python
from converter import convert

queries = convert('Hibernate: select ?\nbinding parameter (1:INTEGER) <- [42]')
```

## Adicionar comandos

Edite `DEFAULT_PREFIXES` em `hibernate_sql/application/conversion.py` e reinicie a aplicação. A chave é o nome exibido na seleção e o valor é inserido antes de cada SQL:

```python
DEFAULT_PREFIXES = {
    'EXPLAIN ANALYZE': 'EXPLAIN ANALYZE',
    'EXPLAIN': 'EXPLAIN',
    'EXPLAIN com buffers': 'EXPLAIN (ANALYZE, BUFFERS)',
}
```

Também é possível injetar um dicionário próprio ao criar `ConversionService`, sem alterar a configuração padrão.

## Comportamento e limites

- Reconhece `org.hibernate.SQL :` e `Hibernate:` e remove a duplicação consecutiva da mesma SQL sem binds entre elas. Execuções que já possuem binds são preservadas.
- Aceita SQL simples sem cabeçalho, começando por um comando reconhecido, como SELECT, WITH, INSERT ou UPDATE. Texto de log sem SQL é rejeitado.
- Substitui parâmetros pela posição, incluindo posições maiores que 9 e binds fora de ordem.
- Trata números sem perda de precisão, booleanos, NULL, textos com aspas/barras, datas, horários e UUIDs. Outros tipos são representados como texto SQL.
- Preserva linhas vazias e interrogações dentro de strings, identificadores, dollar quoting e comentários SQL, inclusive comentários aninhados.
- Recusa parâmetros ausentes, excedentes, repetidos ou com posição zero; bindings malformados; blocos SQL vazios; números inválidos ou não finitos; booleanos inválidos e regiões SQL sem fechamento.
- Aceita várias queries e SQL em várias linhas. Cole blocos de uma execução por vez: logs intercalados de threads diferentes precisam ser separados antes da conversão.
- `?` usado como operador PostgreSQL fora de regiões protegidas é interpretado como placeholder.
- Valores truncados, binários, arrays e objetos que exigem serialização própria não podem ser reconstruídos de forma confiável. Um texto literal `null` não pode ser distinguido de NULL nesse formato de log. Casts não validam o conteúdo de datas ou UUIDs; essa validação pertence ao PostgreSQL.

Os logs são processados localmente e não são gravados. Nenhuma query é executada pela aplicação. Ao executar EXPLAIN ANALYZE no PostgreSQL, o banco executa a instrução, inclusive INSERT/UPDATE/DELETE.

A tela bloqueia envios simultâneos. Limpar os campos invalida resultados pendentes para que respostas antigas não preencham novamente a saída.

## API local

| Rota | Comportamento |
| --- | --- |
| `GET /` | Interface web |
| `GET /prefixes` | Lista de comandos disponíveis |
| `POST /convert` | Objeto JSON com `log` e `prefix` opcional; retorna `sql` e `count` |

O POST exige `Content-Type: application/json`, corpo UTF-8 e um único `Content-Length` válido. O limite é de 5.000.000 bytes do corpo completo, incluindo o JSON; o timeout de inatividade de leitura é de 10 segundos. Transfer-Encoding não é suportado. Erros retornam JSON com a chave `error`: 400 para entrada inválida, 408 para tempo excedido, 413 para tamanho excedido e 415 para tipo de conteúdo inválido. Rotas desconhecidas retornam 404. Os arquivos da interface são servidos por uma lista explícita de rotas.

## Testes

Na raiz do projeto:

```sh
python3 -m unittest discover -v
npm test
```

Os testes Python verificam regras de domínio, contratos do caso de uso, parser, regressões, argumentos de execução, dependências arquiteturais e requisições HTTP reais. Os testes JavaScript verificam o cliente HTTP, carregamento de comandos, conversão, erros, cópia, limpeza e respostas fora de ordem. Não executam um navegador real nem validam consultas em um banco PostgreSQL.

Para medir cobertura sem instalar pacotes:

```sh
python3 -m tools.check_coverage
npm run test:coverage
```

A medição Python inclui as threads do servidor e gera arquivos `.cover` em `coverage/`, ignorada pelo Git. Linhas marcadas com `>>>>>>` não foram executadas; o corpo abstrato do protocolo não é chamado pelo aplicativo. O relatório JavaScript mostra linhas, funções e ramificações. Cobertura de linhas complementa as verificações de comportamento e não garante ausência de defeitos.

Os testes HTTP precisam de permissão para abrir sockets locais. Em ambientes que bloqueiam sockets, a parte independente do servidor pode ser executada com:

```sh
python3 -m unittest tests.test_domain tests.test_application tests.test_bootstrap tests.test_regression tests.test_architecture tests.test_http.RequestValidationTests
```
