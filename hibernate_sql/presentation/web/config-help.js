const pattern = "%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [%thread] %logger : %msg%n";

export const CONFIGURATIONS = {
  yaml: {
    note: 'application.yml ou application.yaml: use o arquivo do perfil de desenvolvimento, como application-dev.yml. Mescle as chaves spring e logging que já existirem. O padrão abaixo é para o Logback padrão do Spring Boot.',
    code: `spring:
  jpa:
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        highlight_sql: false

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
  pattern:
    console: "${pattern}"
`,
  },
  properties: {
    note: 'application.properties: alternativa ao YAML. Use o arquivo do perfil ativo, como application-dev.properties. Atualize as propriedades existentes em vez de duplicá-las. O padrão abaixo é para o Logback padrão do Spring Boot.',
    code: `spring.jpa.show-sql=false
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.highlight_sql=false

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
logging.pattern.console=${pattern}
`,
  },
  logback: {
    note: 'logback-spring.xml (recomendado no Spring Boot) ou logback.xml: use se o projeto já controla o logging por XML. Este é um exemplo mínimo; incorpore os loggers e o padrão ao appender existente, preservando os demais destinos e filtros.',
    code: `<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>${pattern}</pattern>
    </encoder>
  </appender>
  <logger name="org.hibernate.SQL" level="DEBUG"/>
  <logger name="org.hibernate.orm.jdbc.bind" level="TRACE"/>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
`,
  },
  log4j2: {
    note: 'log4j2-spring.xml ou log4j2.xml: alternativa para projetos que já usam Log4j2. Não basta criar este arquivo se o projeto usa Logback. Este é um exemplo mínimo; mescle com os appenders e filtros existentes.',
    code: `<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="${pattern}"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="org.hibernate.SQL" level="DEBUG"/>
    <Logger name="org.hibernate.orm.jdbc.bind" level="TRACE"/>
    <Root level="INFO">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
`,
  },
};

export function initializeConfigHelp(elements, clipboard) {
  function update() {
    const configuration = CONFIGURATIONS[elements.configFormat.value];
    elements.configCode.value = configuration.code;
    elements.configNote.textContent = configuration.note;
    elements.configStatus.textContent = '';
  }

  elements.configHelp.onclick = () => {
    update();
    elements.configDialog.showModal();
    elements.configDialog.scrollTop = 0;
  };
  elements.configClose.onclick = () => elements.configDialog.close();
  elements.configFormat.onchange = update;
  elements.configCopy.onclick = async () => {
    const code = elements.configCode.value;
    try {
      await clipboard.writeText(code);
      if (elements.configCode.value === code) elements.configStatus.textContent = 'Configuração copiada.';
    } catch {
      if (elements.configCode.value !== code) return;
      elements.configCode.focus();
      elements.configCode.select();
      elements.configStatus.textContent = 'Configuração selecionada. Pressione Ctrl+C (ou ⌘C no Mac) para copiar.';
    }
  };
  update();
}
