#!/usr/bin/env python

# Thanks to: https://github.com/ros-visualization/rqt_common_plugins/blob/groovy-devel/rqt_topic/src/rqt_topic/topic_widget.py

import rospy
import roslib
import roslib.message

import datetime
import time
import sys

import opcua

import logging


global server


#class SubHandler(object):

    #def data_change(self, handle, node, val, attr):
        #print("Python: New data change event", handle, node, val, attr)


class OpcUaROSTopic():

    global server

    def __init__(self, parent, idx, topic_name, topic_type):

        self.type_name = topic_type
        self.name = topic_name

        self.nodes = {}

        self.message_class = None
        try:
            self.message_class = roslib.message.get_message_class(topic_type)
            self.message_instance = self.message_class()
        except Exception as e:
            self.message_class = None
            rospy.logfatal("There is not found message type class " + topic_type)

        #TODO: add option if to get data back
        self._subscribers = {}
        self._handles = {}

        self._recursive_create_items(parent, idx, self.name, self.type_name, self.message_instance, True)

        self._subscriber = rospy.Subscriber(self.name, self.message_class, self.message_callback)
        self._publisher = rospy.Publisher(self.name, self.message_class, queue_size=1)

    def _recursive_create_items(self, parent, idx, topic_name, type_name, message, top_level=False):
        topic_text = topic_name.split('/')[-1]
        if '[' in topic_text:
            topic_text = topic_text[topic_text.index('['):]

        # This are 'complex data'
        if hasattr(message, '__slots__') and hasattr(message, '_slot_types'):
            complex_type = True
            new_node = parent.add_object(opcua.ua.NodeId(topic_name, parent.nodeid.NamespaceIndex),   opcua.ua.QualifiedName(topic_text, parent.nodeid.NamespaceIndex))
            new_node.add_property(opcua.ua.NodeId(topic_name + ".Type", parent.nodeid.NamespaceIndex), opcua.ua.QualifiedName("Type", parent.nodeid.NamespaceIndex), type_name)
            #TODO: add option if to get data back
            if top_level:
                new_node.add_method(opcua.ua.NodeId(topic_name + ".Update", parent.nodeid.NamespaceIndex), opcua.ua.QualifiedName("Update", parent.nodeid.NamespaceIndex), self.opcua_update_callback, [], [])

            for slot_name, type_name in zip(message.__slots__, message._slot_types):
                #splitter = '.'
                #if top_level:
                    #splitter = '/'
                self._recursive_create_items(new_node, idx, topic_name + '/' + slot_name, type_name, getattr(message, slot_name))

        else:
            # This are arrays
            base_type_str, array_size = self._extract_array_info(type_name)
            try:
                base_instance = roslib.message.get_message_class(base_type_str)()
            except (ValueError, TypeError):
                base_instance = None

            if array_size is not None and hasattr(base_instance, '__slots__'):
                complex_type = True
                for index in range(array_size):
                    self._recursive_create_items(parent, idx, topic_name + '[%d]' % index, base_type_str, base_instance)
            else:
                new_node = self._create_node_with_type(parent, idx, topic_name, topic_text, type_name, array_size)
                #TODO: add option if to get data back
                #self._subscribers[topic_name] = server.create_subscription(500, SubHandler())
                #self._handles[topic_name] = self._subscribers[topic_name].subscribe_data_change(new_node)

        self.nodes[topic_name] = new_node

        return

    def _extract_array_info(self, type_str):
        array_size = None
        if '[' in type_str and type_str[-1] == ']':
            type_str, array_size_str = type_str.split('[', 1)
            array_size_str = array_size_str[:-1]
            if len(array_size_str) > 0:
                array_size = int(array_size_str)
            else:
                array_size = 0

        return type_str, array_size

    def _create_node_with_type(self, parent, idx, topic_name, topic_text, type_name, array_size):
        variant = None

        if '[' in type_name:
            type_name = type_name[:type_name.index('[')]

        if type_name == 'bool':
            variant = opcua.ua.Variant(False, opcua.ua.VariantType.Boolean)
        elif type_name == 'byte':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.Byte)
        elif type_name == 'int8':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.SByte)
        elif type_name == 'uint8':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.Byte)
        elif type_name == 'int16':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.Int16)
        elif type_name == 'uint16':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.UInt16)
        elif type_name == 'int32':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.Int32)
        elif type_name == 'uint32':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.UInt32)
        elif type_name == 'int64':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.Int64)
        elif type_name == 'uint64':
            variant = opcua.ua.Variant(0, opcua.ua.VariantType.UInt64)
        elif type_name == 'float32':
            variant = opcua.ua.Variant(0.0, opcua.ua.VariantType.Float)
        elif type_name == 'float64':
            variant = opcua.ua.Variant(0.0, opcua.ua.VariantType.Double)
        elif type_name == 'string':
            variant = opcua.ua.Variant('', opcua.ua.VariantType.String)
        else:
            print type_name
            return None

        if array_size is not None:
            value = [value for i in range(array_size)]

        return parent.add_variable(opcua.ua.NodeId(topic_name, parent.nodeid.NamespaceIndex), opcua.ua.QualifiedName(topic_text, parent.nodeid.NamespaceIndex), variant)

    def message_callback(self, message):
        self.update_value(self.name, message)

    def update_value(self, topic_name, message):
        if hasattr(message, '__slots__') and hasattr(message, '_slot_types'):
            for slot_name in message.__slots__:
                self.update_value(topic_name + '/' + slot_name, getattr(message, slot_name))

        elif type(message) in (list, tuple) and (len(message) > 0) and hasattr(message[0], '__slots__'):

            for index, slot in enumerate(message):
                if topic_name + '[%d]' % index in self.nodes:
                    self.update_value(topic_name + '[%d]' % index, slot)
                else:
                    base_type_str, _ = self._extract_array_info(self.nodes[topic_name].text(self._column_index['type']))
                    self._recursive_create_items(self.nodes[topic_name], topic_name + '[%d]' % index, base_type_str, slot)
            # remove obsolete children
            if len(message) < len(self.nodes[topic_name].get_children()):
                for i in range(len(message), self.nodes[topic_name].childCount()):
                    item_topic_name = topic_name + '[%d]' % i
                    self._recursive_delete_items(self.nodes[item_topic_name])
        else:
            if topic_name in self.nodes:
                self.nodes[topic_name].set_value(repr(message))

    @opcua.uamethod
    def opcua_update_callback(self, parent):
        self._publisher.publish(self.message_instance)
        print self.nodes
        print self._subscribers

    def _recursive_delete_widget_items(self, item):
        def _recursive_remove_items_from_tree(item):
            for index in reversed(range(item.childCount())):
                _recursive_remove_items_from_tree(item.child(index))
            topic_name = item.data(0, Qt.UserRole)
            del self._tree_items[topic_name]
        _recursive_remove_items_from_tree(item)
        item.parent().removeChild(item)


def shutdown():
    global server

    server.stop()


def main(args):

    global server

    rospy.init_node("opcua_server")
    rospy.on_shutdown(shutdown)

    #TODO: setup library logging
    #logging.basicConfig(level=logging.WARN)

    server = opcua.Server()
    server.set_endpoint("opc.tcp://localhost:21554/")
    server.set_server_name("ROS OpcUa Server")

    server.start()

    try:
        # setup our own namespace, this is expected
        uri = "http://ros.org"
        idx = server.register_namespace(uri)

        # get Objects node, this is where we should put our custom stuff
        objects = server.get_objects_node()

        #TODO: Add refresh call from ROS (namespace can be sent as paramter)

        topics = objects.add_object(idx, "ROS-Topics")
        #TODO: Add reading of system state

        ros_topics = rospy.get_published_topics()

        for topic_name, topic_type in ros_topics:
            OpcUaROSTopic(topics, idx, topic_name, topic_type)

        rospy.loginfo("Now doing rospy.spin")
        rospy.spin()

    except rospy.ROSInterruptException:

        server.stop()


if __name__ == "__main__":
    # optional: setup logging
    logging.basicConfig(level=logging.INFO)
    #logger = logging.getLogger("opcua.address_space")
    # logger.setLevel(logging.DEBUG)
    #logger = logging.getLogger("opcua.internal_server")
    #logger.setLevel(logging.DEBUG)
    #logger = logging.getLogger("opcua.binary_server_asyncio")
    # logger.setLevel(logging.DEBUG)
    #logger = logging.getLogger("opcua.uaprocessor")
    # logger.setLevel(logging.DEBUG)
    #logger = logging.getLogger("opcua.subscription_service")
    # logger.setLevel(logging.DEBUG)
    main(sys.argv)
