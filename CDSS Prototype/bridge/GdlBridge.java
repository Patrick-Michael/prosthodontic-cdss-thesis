import com.google.gson.*;
import org.apache.commons.lang3.tuple.Pair;
import org.gdl2.Gdl2;
import org.gdl2.datatypes.*;
import org.gdl2.model.DataBinding;
import org.gdl2.model.Element;
import org.gdl2.model.Guideline;
import org.gdl2.runtime.*;

import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.ZonedDateTime;
import java.util.*;

public class GdlBridge {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java GdlBridge <request.json>");
            System.exit(1);
        }

        Gson gson = new Gson();

        String requestText = new String(
                Files.readAllBytes(Paths.get(args[0])),
                StandardCharsets.UTF_8
        );

        JsonObject request = gson.fromJson(requestText, JsonObject.class);

        String guidelinePath = request.get("guideline").getAsString();
        String guidelineText = new String(
                Files.readAllBytes(Paths.get(guidelinePath)),
                StandardCharsets.UTF_8
        );

        Guideline guideline = Gdl2.fromGdl2(guidelineText);

        Map<String, DataInstance.Builder> builders = new LinkedHashMap<>();

        for (JsonElement item : request.getAsJsonArray("inputs")) {
            JsonObject input = item.getAsJsonObject();

            String elementId = input.get("element_id").getAsString();
            String datatype = input.get("type").getAsString();

            DataBinding binding = findBinding(guideline, elementId);
            Element element = binding.getElements().get(elementId);

            DataInstance.Builder builder = builders.get(binding.getId());

            if (builder == null) {
                builder = new DataInstance.Builder()
                        .modelId(binding.getModelId());

                builders.put(binding.getId(), builder);
            }

            Object value = convertValue(datatype, input);

            builder.addValue(element.getPath(), value);
        }

        List<DataInstance> inputs = new ArrayList<>();

        for (DataInstance.Builder builder : builders.values()) {
            inputs.add(builder.build());
        }

        RuntimeConfiguration configuration =
                RuntimeConfiguration.builder()
                        .objectCreatorPlugin(new DefaultObjectCreator())
                        .terminologySubsumptionEvaluators(Collections.emptyMap())
                        .language("en")
                        .inDebugMode(true)
                        .build();

        Interpreter interpreter = new Interpreter(configuration);

        Interpreter.ExecutionOutput execution =
                interpreter.executeGuidelinesAndGetFiredRules(
                        Collections.singletonList(guideline),
                        inputs
                );

        JsonObject response = new JsonObject();

        response.addProperty(
                "guideline_id",
                guideline.getId()
        );

        response.add(
                "outputs",
                serializeOutputs(execution.getResult())
        );

        response.add(
                "fired_rules",
                gson.toJsonTree(execution.getFiredRules())
        );

        Gson debugGson = new GsonBuilder()
                .registerTypeAdapter(
                        Pair.class,
                        (JsonSerializer<Pair>) (pair, type, context) -> {

                            JsonObject obj = new JsonObject();

                            obj.addProperty(
                                    String.valueOf(pair.getLeft()),
                                    Boolean.parseBoolean(
                                            String.valueOf(pair.getRight())
                                    )
                            );

                            return obj;
                        }
                )
                .setPrettyPrinting()
                .disableHtmlEscaping()
                .create();

        response.add(
                "debug",
                debugGson.toJsonTree(
                        interpreter
                                .getDebugExecution()
                                .getGuidelinesInOrderOfExecution()
                )
        );

        System.out.println(
                new GsonBuilder()
                        .setPrettyPrinting()
                        .disableHtmlEscaping()
                        .create()
                        .toJson(response)
        );
    }


    private static DataBinding findBinding(
            Guideline guideline,
            String elementId
    ) {

        for (DataBinding binding :
                guideline.getDefinition()
                        .getDataBindings()
                        .values()) {

            if (binding.getElements().containsKey(elementId)) {
                return binding;
            }
        }

        throw new IllegalArgumentException(
                "Unknown guideline element: " + elementId
        );
    }


    private static Object convertValue(
            String datatype,
            JsonObject input
    ) {

        switch (datatype.toLowerCase()) {

            case "datetime":
                return ZonedDateTime.parse(
                        input.get("value").getAsString()
                );


            case "date":
                return DvDate.valueOf(
                        input.get("value").getAsString()
                );


            case "quantity":
                return new DvQuantity(
                        input.get("unit").getAsString(),
                        input.get("value").getAsDouble(),
                        input.get("precision").getAsInt()
                );


            case "proportion":
                return new org.openehr.rm.datatypes.quantity.DvProportion(
                        input.get("numerator").getAsDouble(),
                        input.get("denominator").getAsDouble(),

                        org.openehr.rm.datatypes.quantity.ProportionKind.valueOf(
                                input.get("proportion_type").getAsInt()
                        ),

                        input.get("precision").getAsInt()
                );


            case "count":
                return DvCount.valueOf(
                        input.get("value").getAsInt()
                );


            case "boolean":
                return input.get("value").getAsBoolean();


            case "coded_text":
                return new DvCodedText(
                        input.get("value").getAsString(),
                        input.get("terminology").getAsString(),
                        input.get("code").getAsString()
                );


            case "text":
                return input.get("value").getAsString();


            default:
                throw new IllegalArgumentException(
                        "Unsupported datatype: " + datatype
                );
        }
    }


    private static JsonArray serializeOutputs(
            List<DataInstance> results
    ) {

        JsonArray outputArray = new JsonArray();

        for (DataInstance result : results) {

            JsonObject item = new JsonObject();

            item.addProperty(
                    "model_id",
                    result.modelId()
            );

            item.addProperty(
                    "instance_id",
                    result.id()
            );

            JsonObject values = new JsonObject();

            for (Map.Entry<String, Object> entry :
                    result.values().entrySet()) {

                JsonObject value = new JsonObject();

                Object raw = entry.getValue();

                value.addProperty(
                        "type",
                        raw == null
                                ? "null"
                                : raw.getClass().getSimpleName()
                );

                value.addProperty(
                        "value",
                        raw == null
                                ? null
                                : raw.toString()
                );

                values.add(
                        entry.getKey(),
                        value
                );
            }

            item.add(
                    "values",
                    values
            );

            outputArray.add(item);
        }

        return outputArray;
    }
}