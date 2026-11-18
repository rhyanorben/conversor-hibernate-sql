const pattern = "%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [%thread] %logger : %msg%n";

export const CONFIGURATIONS = {
  yaml: {
    note: 'Use o arquivo do perfil ativo, como application-dev.yml. Mescle com as chaves existentes. O bloco jpa fica dentro de spring, e org.hibernate é o nome completo do pacote dos loggers.',
    code: `spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
    show-sql: true

logging.level.org.hibernate:
  SQL: DEBUG
  orm.jdbc.bind: TRACE
`,
  },
  properties: {
    note: 'Use o arquivo do perfil ativo, como application-dev.properties. Atualize as propriedades já definidas nesse arquivo.',
    code: `spring.jpa.properties.hibernate.format_sql=true
spring.jpa.show-sql=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
`,
  },
  logback: {
    note: 'Para projetos com Logback. Em um XML existente, incorpore os loggers e ajuste o padrão do appender, preservando os demais destinos e filtros. Configure as opções JPA também no arquivo da aplicação.',
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
    note: 'Para projetos com Log4j2. Em um XML existente, incorpore os loggers e ajuste o padrão do appender, preservando os demais destinos e filtros. Configure as opções JPA também no arquivo da aplicação.',
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
