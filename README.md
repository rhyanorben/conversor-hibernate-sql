# Hibernate → PostgreSQL

Aplicação que reconstrói SQL PostgreSQL a partir dos logs de SQL e binding do Hibernate. Para executar localmente, usa Python 3.8+ e apenas a biblioteca padrão, sem dependências para instalar. Para publicar na nuvem, usa Gunicorn e Python 3.13, conforme os arquivos de configuração do projeto. Node.js 22+ é necessário somente para os testes do JavaScript. A aplicação não se conecta ao banco.

## Hospedado na WEB

https://conversor-hibernate-sql.onrender.com/

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

## Publicar no Render

O projeto inclui `requirements.txt` para instalar o servidor Gunicorn, `.python-version` para selecionar Python 3.13 e `render.yaml` para criar um serviço gratuito por Blueprint. A entrada de publicação é `app:application`; o comando `python3 app.py` continua disponível para uso local.

Se o primeiro deploy falhou com `Could not open requirements file`, o Render tentou instalar um arquivo que ainda não estava no código publicado. Envie todos os arquivos atualizados deste projeto ao GitHub, na mesma branch selecionada no serviço do Render. Confira que `requirements.txt`, `.python-version` e `app.py` estão na raiz dessa branch.

Para configurar um serviço já criado:

1. Abra o serviço no painel do Render e entre em **Settings → Build & Deploy**.
2. Confirme o repositório e a branch que receberam os arquivos. Deixe **Root Directory** vazio, pois a aplicação está na raiz do repositório.
3. Use a linguagem **Python 3** e os comandos abaixo.

   **Build Command:**

   ```sh
   python -m pip install -r requirements.txt
   ```

   **Start Command:**

   ```sh
   gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 30 app:application
   ```

4. Mantenha a instância **Free** e configure **Health Check Path** como `/`. Salve as alterações. Se houver uma variável `PYTHON_VERSION` antiga em **Environment**, remova-a para usar a versão definida em `.python-version`.
5. Selecione **Manual Deploy → Deploy latest commit** e acompanhe os registros até o serviço ficar disponível.
6. Abra o endereço `https://nome-do-servico.onrender.com` exibido no painel. Teste uma conversão com dados fictícios, a opção de comando e o botão de copiar.

O `render.yaml` é uma alternativa para criar e gerenciar um serviço por **New → Blueprint**, escolhendo este repositório. Adicionar esse arquivo ao GitHub não altera automaticamente as configurações de um serviço criado manualmente; nesse caso, siga os ajustes acima. Não é preciso criar outro serviço para corrigir o primeiro deploy.

O Render fornece o endereço e HTTPS, sem exigir um domínio próprio. No plano gratuito, o serviço pode entrar em repouso e demorar a responder no próximo acesso. Consulte a [documentação de serviços web](https://render.com/docs/web-services), as [limitações do plano gratuito](https://render.com/docs/free) e a [seleção da versão do Python](https://render.com/docs/python-version).

## Organização e dependências

### Ícone da guia do navegador

O ícone representa um banco de dados com uma seta de conversão, em azul e verde.
O desenho editável fica em `hibernate_sql/presentation/web/favicon.svg`; a versão
`favicon.ico` inclui os tamanhos 16, 32 e 48 pixels para compatibilidade.
Ambos são servidos pela aplicação local e pela publicação WSGI, sem configuração
adicional no Render. Ao alterar o desenho, atualize também a versão `.ico`.

### Estrutura do projeto

```text
app.py                            Entrada local e aplicação WSGI para publicação
converter.py                      API compatível: convert, literal, substitute
requirements.txt                  Gunicorn para execução na nuvem
.python-version                   Versão do Python no Render
render.yaml                       Configuração do serviço gratuito por Blueprint
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
    wsgi.py                       Entrada HTTP para o servidor de publicação
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

Os logs são enviados pelo navegador ao servidor desta aplicação para conversão. Na execução local, esse servidor fica no seu computador; na nuvem, o processamento ocorre no provedor de hospedagem. A aplicação não grava o corpo das requisições nem os logs enviados e não possui login: quem tiver acesso ao endereço poderá usar a ferramenta. Nenhuma query é executada pela aplicação. Ao executar EXPLAIN ANALYZE no PostgreSQL, o banco executa a instrução, inclusive INSERT/UPDATE/DELETE.

A tela bloqueia envios simultâneos. Limpar os campos invalida resultados pendentes para que respostas antigas não preencham novamente a saída.

## API

| Rota | Comportamento |
| --- | --- |
| `GET /` | Interface web |
| `GET /prefixes` | Lista de comandos disponíveis |
| `POST /convert` | Objeto JSON com `log` e `prefix` opcional; retorna `sql` e `count` |

O POST exige `Content-Type: application/json`, corpo UTF-8 e um `Content-Length` válido. O limite é de 5.000.000 bytes do corpo completo, incluindo o JSON. Erros da aplicação retornam JSON com a chave `error`: 400 para entrada inválida, 413 para tamanho excedido e 415 para tipo de conteúdo inválido. Rotas desconhecidas retornam 404. Os arquivos da interface são servidos por uma lista explícita de rotas.

No servidor local, o timeout de inatividade de leitura é de 10 segundos, com resposta JSON 408 em caso de tempo excedido; cabeçalhos `Content-Length` duplicados e Transfer-Encoding são rejeitados. Na publicação WSGI, o Gunicorn recebe e valida as requisições HTTP antes de repassá-las à aplicação. O comando sugerido configura um timeout de 30 segundos para os workers do Gunicorn; ele não equivale ao timeout de leitura do servidor local nem garante uma resposta JSON 408.

## Testes

Na raiz do projeto:

```sh
python3 -m unittest discover -v
npm test
```

Os testes Python verificam regras de domínio, contratos do caso de uso, parser, regressões, argumentos de execução, dependências arquiteturais, requisições HTTP reais e o contrato WSGI usado na publicação. Os testes JavaScript verificam o cliente HTTP, carregamento de comandos, conversão, erros, cópia, limpeza e respostas fora de ordem. Não executam um navegador real nem validam consultas em um banco PostgreSQL.

Para medir cobertura sem instalar pacotes:

```sh
python3 -m tools.check_coverage
npm run test:coverage
```

A medição Python inclui as threads do servidor e gera arquivos `.cover` em `coverage/`, ignorada pelo Git. Linhas marcadas com `>>>>>>` não foram executadas; o corpo abstrato do protocolo não é chamado pelo aplicativo. O relatório JavaScript mostra linhas, funções e ramificações. Cobertura de linhas complementa as verificações de comportamento e não garante ausência de defeitos.

Os testes HTTP precisam de permissão para abrir sockets locais. Em ambientes que bloqueiam sockets, a parte independente do servidor pode ser executada com:

```sh
python3 -m unittest tests.test_domain tests.test_application tests.test_bootstrap tests.test_regression tests.test_architecture tests.test_http.RequestValidationTests tests.test_wsgi
```
